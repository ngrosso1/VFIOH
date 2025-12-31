import threading
import sys
import json
import os
import io
import time
import tty
import termios
import subprocess

from kernelUpdates import installations, kernelBootChanges_no_prompt
from vmCreation import get_sys_info, create_vm, modify_storage_bus, update_display_to_vnc, cleanupDrives
from getISO import ensure_libvirt_access, virtioDrivers
from hooks.hooks import setup_libvirt_hooks, update_start_sh, update_revert_sh, add_gpu_passthrough_devices
from moving import main_moving
from troubleshoot_orchestrator import TroubleshootOrchestrator

PROGRESS_FILE = "progress.json"

def saveProgress(choice, step, data=None):
    progress = {"choice": choice, "step": step}
    if data:
        progress["data"] = data
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f)

def loadProgress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r") as f:
            return json.load(f)
    return None

def clearProgress():
    if os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)

def get_distro():
    """Get the current distribution from /etc/os-release"""
    with open("/etc/os-release", "r") as f:
        for line in f:
            if line.lower().startswith("id="):
                return line.strip().split("=")[1].strip('"').lower()
    return None

def get_key():
    """Get a single keypress from the terminal"""
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        key = sys.stdin.read(1)
        # Handle arrow keys (they send 3 characters: \x1b[A, \x1b[B, etc.)
        if key == '\x1b':
            key += sys.stdin.read(2)
        return key
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

# ANSI color codes
BLUE = "\033[1;32m"
RESET = "\033[0m"

def show_menu(options, title="Menu"):
    """
    Display an interactive menu with arrow key navigation
    
    Args:
        options: List of tuples (display_text, return_value)
        title: Title to display above the menu (can be None to skip)
    
    Returns:
        The return_value of the selected option
    """
    selected = 0
    
    while True:
        # Clear screen and move cursor to top
        print("\033[2J\033[H", end="", flush=True)

        # Print ASCII art header
        print(f"{BLUE}")
        print(r" _    ________________  __  __")
        print(r"| |  / / ____/  _/ __ \/ / / /")
        print(r"| | / / /_   / // / / / /_/ / ")
        print(r"| |/ / __/ _/ // /_/ / __  /  ")
        print(r"|___/_/   /___/\____/_/ /_/   ")
        print(f"{RESET}")
        print("Welcome! What would you like to do?")
        print("\nUse ↑/↓ arrow keys to navigate, Enter to select:\n")
        
        # Print menu options
        for i, (text, _) in enumerate(options):
            if i == selected:
                print(f"  > \033[4m{text}\033[0m")  # Underlined for selected item
            else:
                print(f"    {text}")
        
        key = get_key()
        
        # Handle arrow keys
        if key == '\x1b[A':  # Up arrow
            selected = (selected - 1) % len(options)
        elif key == '\x1b[B':  # Down arrow
            selected = (selected + 1) % len(options)
        elif key == '\r' or key == '\n':  # Enter
            return options[selected][1]
        elif key == '\x03':  # Ctrl + C
            print("\n\nExiting...")
            sys.exit(0)

class Api:
    def __init__(self):
        self.distro = get_distro()

    def _run_in_thread(self, target, args=()):
        thread = threading.Thread(target=target, args=args)
        thread.daemon = True
        thread.start()

    def _log_and_run(self, func, *args):
        # Create a string buffer to capture output
        output_buffer = io.StringIO()
        
        # Redirect stdout to our buffer
        old_stdout = sys.stdout
        sys.stdout = output_buffer
        
        try:
            func(*args)
        except Exception as e:
            print(f"An error occurred: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Restore stdout
            sys.stdout = old_stdout
            
            # Get the captured output
            output = output_buffer.getvalue()
            output_buffer.close()
            
            for line in output.splitlines():
                self.log_message(line)
                time.sleep(0.01)  # Prevents flooding

    def log_message(self, msg):
        if not isinstance(msg, str):
            msg = str(msg)
        print(msg)
    
    def _get_available_vms(self):
        """Get list of all VMs with their status"""
        try:
            # Get all VMs
            result = subprocess.run(
                ["virsh", "list", "--all", "--name"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode != 0:
                return None, "Failed to list VMs"
            
            vm_names = [name.strip() for name in result.stdout.strip().split('\n') if name.strip()]
            
            if not vm_names:
                return [], None
            
            # Get status for each VM
            vms_with_status = []
            for vm_name in vm_names:
                status_result = subprocess.run(
                    ["virsh", "domstate", vm_name],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                if status_result.returncode == 0:
                    status = status_result.stdout.strip()
                    is_running = status.lower() in ["running", "paused"]
                    vms_with_status.append((vm_name, is_running))
                else:
                    vms_with_status.append((vm_name, False))
            
            return vms_with_status, None
            
        except FileNotFoundError:
            return None, "virsh command not found. Is libvirt installed?"
        except subprocess.TimeoutExpired:
            return None, "Timeout while listing VMs"
        except Exception as e:
            return None, f"Error listing VMs: {str(e)}"
    
    def _select_vm(self):
        """Show VM selection menu and return selected VM name"""
        vms_with_status, error = self._get_available_vms()
        
        if error:
            print(f"\033[91m{error}\033[0m")
            input("\nPress Enter to continue...")
            return None
        
        if not vms_with_status:
            print("\033[91mNo VMs found. Please create a VM first.\033[0m")
            input("\nPress Enter to continue...")
            return None
        
        # Build menu options
        menu_options = []
        for vm_name, is_running in vms_with_status:
            if is_running:
                display_text = f"{vm_name} \033[93m(⚠️  RUNNING - PLEASE STOP THIS VM BEFORE CONTINUING)\033[0m"
            else:
                display_text = vm_name
            menu_options.append((display_text, vm_name))
        
        menu_options.append(("Back to Custom Functions Menu", "back"))
        
        selected = show_menu(menu_options, title="Select VM")
        
        if selected == "back":
            return None
        
        return selected

    def start_choice_1(self):
        self._run_in_thread(self._execute_choice_1)

    def _execute_choice_1(self):
        saveProgress(1, 1)
        self.log_message("Starting Step 1: Preparing Host System...")
        
        # Test message to verify logging is working
        self.log_message("DEBUG: Testing log output...")
        
        self.log_message("\n--- Running Installations ---")
        try:
            self._log_and_run(installations, self.distro)
            self.log_message("DEBUG: Installations completed")
            saveProgress(1, 2)
        except Exception as e:
            self.log_message(f"ERROR in installations: {e}")
            return
        
        self.log_message("\n--- Applying Kernel Boot Changes ---")
        try:
            self._log_and_run(kernelBootChanges_no_prompt, self.distro)
            self.log_message("DEBUG: Kernel boot changes completed")
            saveProgress(1, 3)
        except Exception as e:
            self.log_message(f"ERROR in kernelBootChanges_no_prompt: {e}")
            return
        
        self.log_message("\nHost preparation complete. A reboot is required")
        self.log_message("You can reboot from your system menu, or run 'sudo reboot' in a terminal")
        self.log_message("After rebooting, please run this application again and choose option 2")
        saveProgress(1, "complete")

    def start_choice_2(self):
        self._execute_choice_2()

    def _execute_choice_2(self):
        saveProgress(2, 1)
        self.log_message("Starting Step 2: Creating VM and Setting Up GPU Passthrough...")
        
        self.log_message("\n--- Getting System Information ---")
        try:
            sys_info = get_sys_info()
            saveProgress(2, 2, {"sys_info": sys_info})
            self.log_message(f"System info gathered: {sys_info}")
        except Exception as e:
            self.log_message(f"ERROR getting system info: {e}")
            return
        
        self.log_message("\n--- Ensuring Libvirt Access ---")
        try:
            ensure_libvirt_access("/var/lib/libvirt/images/")
            saveProgress(2, 3)
        except Exception as e:
            self.log_message(f"ERROR ensuring libvirt access: {e}")
            return

        self.log_message("\n--- Creating VM ---")
        try:
            vm_name = create_vm(self.distro)
            saveProgress(2, 5, {"vm_name": vm_name})
            self.log_message(f"VM created: {vm_name}")
        except Exception as e:
            self.log_message(f"ERROR creating VM: {e}")
            return
        
        self.log_message("\n--- Modifying Storage Bus ---")
        try:
            modify_storage_bus(vm_name)
            saveProgress(2, 6)
        except Exception as e:
            self.log_message(f"ERROR modifying storage bus: {e}")
            return
        
        self.log_message("\n--- Updating Display to VNC ---")
        try:
            update_display_to_vnc(vm_name, self.distro)
            saveProgress(2, 7)
        except Exception as e:
            self.log_message(f"ERROR updating display: {e}")
            return
        
        self.log_message("\n--- Cleaning Up Drives ---")
        try:
            cleanupDrives(vm_name)
            saveProgress(2, 8)
        except Exception as e:
            self.log_message(f"ERROR cleaning up drives: {e}")
            return
        
        self.log_message("\n--- Setting Up Libvirt Hooks ---")
        try:
            setup_libvirt_hooks(vm_name)
            saveProgress(2, 9)
        except Exception as e:
            self.log_message(f"ERROR setting up hooks: {e}")
            return
        
        self.log_message("\n--- Updating start.sh Script ---")
        try:
            update_start_sh(vm_name)
            saveProgress(2, 10)
        except Exception as e:
            self.log_message(f"ERROR updating start.sh: {e}")
            return
        
        self.log_message("\n--- Updating revert.sh Script ---")
        try:
            update_revert_sh(vm_name)
            saveProgress(2, 11)
        except Exception as e:
            self.log_message(f"ERROR updating revert.sh: {e}")
            return
        
        self.log_message("\n--- Adding GPU Passthrough Devices ---")
        try:
            add_gpu_passthrough_devices(vm_name)
            saveProgress(2, 12)
        except Exception as e:
            self.log_message(f"ERROR adding GPU passthrough: {e}")
            return
        
        self.log_message("\n=== VM Setup Complete! ===")
        self.log_message(f"Your VM '{vm_name}' is ready with GPU passthrough configured")
        clearProgress()

    def start_choice_3(self):
        self._run_in_thread(self._execute_choice_3)

    def _execute_choice_3(self):
        self.log_message("Checking for saved progress...")
        progress = loadProgress()
        
        if not progress:
            self.log_message("No saved progress found. Please start from the beginning")
            return
        
        choice = progress.get("choice")
        step = progress.get("step")
        data = progress.get("data", {})
        
        self.log_message(f"Found saved progress: Choice {choice}, Step {step}")
        
        if choice == 1:
            self.log_message("Choice 1 (Host preparation) was in progress")
            self.log_message("Please restart Choice 1 from the beginning as kernel changes cannot be partially resumed")
            return
        
        if choice == 2:
            self.log_message("Resuming VM creation from saved checkpoint...")
            vm_name = data.get("vm_name", "win11")
            
            if step < 5:
                self.log_message("Restarting from the beginning of VM creation...")
                self._execute_choice_2()
            elif step == 5:
                self.log_message(f"Resuming with VM: {vm_name}")
                self.log_message("\n--- Modifying Storage Bus ---")
                modify_storage_bus(vm_name)
                saveProgress(2, 6)
                self._continue_choice_2_from_step_6(vm_name)
            else:
                self.log_message(f"Resuming from step {step}...")
                self._continue_choice_2_from_step(vm_name, step)

    def _continue_choice_2_from_step_6(self, vm_name):
        """Continue choice 2 from step 6 onwards"""
        self.log_message("\n--- Updating Display to VNC ---")
        update_display_to_vnc(vm_name, self.distro)
        saveProgress(2, 7)
        
        self.log_message("\n--- Cleaning Up Drives ---")
        cleanupDrives(vm_name)
        saveProgress(2, 8)
        
        self.log_message("\n--- Setting Up Libvirt Hooks ---")
        setup_libvirt_hooks(vm_name)
        saveProgress(2, 9)
        
        self.log_message("\n--- Updating start.sh Script ---")
        update_start_sh(vm_name)
        saveProgress(2, 10)
        
        self.log_message("\n--- Updating revert.sh Script ---")
        update_revert_sh(vm_name)
        saveProgress(2, 11)
        
        self.log_message("\n--- Adding GPU Passthrough Devices ---")
        add_gpu_passthrough_devices(vm_name)
        saveProgress(2, 12)
        
        self.log_message("\n=== VM Setup Complete! ===")
        self.log_message(f"Your VM '{vm_name}' is ready with GPU passthrough configured")
        clearProgress()

    def _continue_choice_2_from_step(self, vm_name, step):
        """Continue from any step in choice 2"""
        # This is a simplified version - expand as needed
        if step >= 6:
            self._continue_choice_2_from_step_6(vm_name)

    def start_choice_4(self):
        """Execute choice 4 - Custom Functions Menu (runs synchronously for interactive menu)"""
        while True:
            function_options = [
                ("Function 1    -   Installations", "1"),
                ("Function 2    -   Kernel Boot Changes", "2"),
                ("Function 3    -   Create VM", "3"), #TODO
                ("Function 4    -   Modifying Storage Bus", "4"),
                ("Function 5    -   Updating Display to VNC", "5"),
                ("Function 6    -   Cleaning Up Drives", "6"),
                ("Function 7    -   Setting Up Libvirt Hooks", "7"),
                ("Function 8    -   Updating start.sh Script", "8"),
                ("Function 9    -   Updating revert.sh Script", "9"),
                ("Function 10   -   Adding GPU Passthrough Devices", "10"),
                ("Back to Main Menu", "back")
            ]
            
            selection = show_menu(function_options, title="Custom Functions")
            
            # Clear screen for execution
            print("\033[2J\033[H", end="", flush=True)
            
            if selection == "1":
                installations(self.distro)
                input("\nPress Enter to continue...")
            elif selection == "2":
                kernelBootChanges_no_prompt(self.distro)
                input("\nPress Enter to continue...")
            elif selection == "3":
                vm_name = create_vm(self.distro)
                input("\nPress Enter to continue...")
            elif selection == "4":
                # Clear screen for execution
                print("\033[2J\033[H", end="", flush=True)
                vm_name = self._select_vm()
                if vm_name:
                    print("\033[2J\033[H", end="", flush=True)
                    try:
                        modify_storage_bus(vm_name)
                        print("\033[92mStorage bus modification complete!\033[0m")
                    except Exception as e:
                        print(f"\033[91mError: {e}\033[0m")
                    input("\nPress Enter to continue...")
            elif selection == "5":
                # Clear screen for execution
                print("\033[2J\033[H", end="", flush=True)
                vm_name = self._select_vm()
                if vm_name:
                    print("\033[2J\033[H", end="", flush=True)
                    try:
                        update_display_to_vnc(vm_name, self.distro)
                        print("\033[92mDisplay update complete!\033[0m")
                    except Exception as e:
                        print(f"\033[91mError: {e}\033[0m")
                    input("\nPress Enter to continue...")
            elif selection == "6":
                # Clear screen for execution
                print("\033[2J\033[H", end="", flush=True)
                vm_name = self._select_vm()
                if vm_name:
                    print("\033[2J\033[H", end="", flush=True)
                    try:
                        cleanupDrives(vm_name)
                        print("\033[92mDrive cleanup complete!\033[0m")
                    except Exception as e:
                        print(f"\033[91mError: {e}\033[0m")
                    input("\nPress Enter to continue...")
            elif selection == "7":
                # Clear screen for execution
                print("\033[2J\033[H", end="", flush=True)
                vm_name = self._select_vm()
                if vm_name:
                    print("\033[2J\033[H", end="", flush=True)
                    try:
                        setup_libvirt_hooks(vm_name)
                        print("\033[92mLibvirt hooks setup complete!\033[0m")
                    except Exception as e:
                        print(f"\033[91mError: {e}\033[0m")
                    input("\nPress Enter to continue...")
            elif selection == "8":
                # Clear screen for execution
                print("\033[2J\033[H", end="", flush=True)
                vm_name = self._select_vm()
                if vm_name:
                    print("\033[2J\033[H", end="", flush=True)
                    try:
                        update_start_sh(vm_name)
                        print("\033[92mstart.sh update complete!\033[0m")
                    except Exception as e:
                        print(f"\033[91mError: {e}\033[0m")
                    input("\nPress Enter to continue...")
            elif selection == "9":
                # Clear screen for execution
                print("\033[2J\033[H", end="", flush=True)
                vm_name = self._select_vm()
                if vm_name:
                    print("\033[2J\033[H", end="", flush=True)
                    try:
                        update_revert_sh(vm_name)
                        print("\033[92mrevert.sh update complete!\033[0m")
                    except Exception as e:
                        print(f"\033[91mError: {e}\033[0m")
                    input("\nPress Enter to continue...")
            elif selection == "10":
                # Clear screen for execution
                print("\033[2J\033[H", end="", flush=True)
                vm_name = self._select_vm()
                if vm_name:
                    print("\033[2J\033[H", end="", flush=True)
                    try:
                        add_gpu_passthrough_devices(vm_name)
                        print("\033[92mGPU passthrough devices added!\033[0m")
                    except Exception as e:
                        print(f"\033[91mError: {e}\033[0m")
                    input("\nPress Enter to continue...")
            elif selection == "back":
                break
        
    def start_choice_5(self):
        """Execute choice 5 - Moving VMs (runs synchronously for interactive menu)"""
        main_moving()
    
    def start_choice_6(self):
        """Execute choice 6 - AI Troubleshooting"""
        troubleshooter = TroubleshootOrchestrator()
        
        # Check if there's a saved VM name from progress
        progress = loadProgress()
        vm_name = None
        failed_step = None
        
        if progress:
            vm_name = progress.get("data", {}).get("vm_name")
            failed_step = f"Step {progress.get('choice')}.{progress.get('step')}"
        
        try:
            troubleshooter.interactive_troubleshoot(vm_name, failed_step)
        except KeyboardInterrupt:
            print(f"\n\n\033[93mTroubleshooting interrupted{RESET}")
        except Exception as e:
            print(f"\n\033[91mError during troubleshooting: {e}{RESET}")
            import traceback
            traceback.print_exc()
        
        # No "Press Enter" prompt - just return to menu

def run_terminal_mode():
    """Run the application in terminal mode"""
    api = Api()
    
    # Requesting to be run as root
    if os.geteuid() != 0:
        print("Root privileges are required. Please run with sudo")
        sys.exit(1)
    
    while True:
        menu_options = [
            ("Prepare Host System (Kernel Updates & Reboot)", "1"),
            ("Create VM & Passthrough GPU", "2"),
            ("Resume Previous Setup", "3"),
            ("Custom Functions --- (Advanced)", "4"),
            ("Moving VMs", "5"),
            ("AI Troubleshooting", "6"),
            ("Exit", "7")
        ]
        
        choice = show_menu(menu_options)

        # Clearing screen
        print("\033[2J\033[H", end="", flush=True)
        
        if choice == "1":
            api.start_choice_1()
            time.sleep(1)
            input("\nPress Enter to continue...")
        elif choice == "2":
            api.start_choice_2()
            time.sleep(1)
            input("\nPress Enter to continue...")
        elif choice == "3":
            api.start_choice_3()
            time.sleep(1)
            input("\nPress Enter to continue...")
        elif choice == "4":
            api.start_choice_4()
            time.sleep(1)
        elif choice == "5":
            api.start_choice_5()
            time.sleep(1)
        elif choice == "6":
            api.start_choice_6()
            # No sleep needed, goes straight back to menu
        elif choice == "7":
            print("Exiting...")
            break

if __name__ == "__main__":
    run_terminal_mode()