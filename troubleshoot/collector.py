"""
Log and system state collection for troubleshooting
"""

import subprocess
import os
import json
from datetime import datetime
from pathlib import Path

class LogCollector:
    def __init__(self, log_dir="logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
    def collect_all(self, vm_name=None, failed_step=None):
        """Collect all relevant logs and system state"""
        report = {
            "timestamp": self.timestamp,
            "failed_step": failed_step,
            "vm_name": vm_name,
            "system_info": self._get_system_info(),
            "kernel_logs": self._get_dmesg(),
            "libvirt_logs": self._get_libvirt_logs(vm_name),
            "gpu_status": self._get_gpu_status(),
            "iommu_groups": self._get_iommu_groups(),
            "module_status": self._get_module_status(),
            "service_status": self._get_service_status(),
            "grub_config": self._get_grub_config(),
            "vfio_config": self._get_vfio_config(),
        }
        
        # Save to file
        log_file = self.log_dir / f"diagnostic_{self.timestamp}.json"
        with open(log_file, "w") as f:
            json.dump(report, f, indent=2)
        
        print(f"Diagnostic data saved to: {log_file}")
        return report, log_file
    
    def _run_cmd(self, cmd, shell=False):
        """Run command and capture output safely"""
        try:
            if shell:
                result = subprocess.run(
                    cmd, 
                    shell=True, 
                    capture_output=True, 
                    text=True, 
                    timeout=30
                )
            else:
                result = subprocess.run(
                    cmd, 
                    capture_output=True, 
                    text=True, 
                    timeout=30
                )
            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out"}
        except Exception as e:
            return {"error": str(e)}
    
    def _get_system_info(self):
        """Collect basic system information"""
        info = {
            "distro": self._get_distro(),
            "kernel": self._run_cmd(["uname", "-r"])["stdout"].strip(),
            "cpu": self._get_cpu_info(),
            "gpu": self._get_gpu_info(),
        }
        return info
    
    def _get_distro(self):
        """Get distribution name"""
        try:
            with open("/etc/os-release", "r") as f:
                for line in f:
                    if line.lower().startswith("id="):
                        return line.strip().split("=")[1].strip('"').lower()
        except:
            return "unknown"
        return "unknown"
    
    def _get_cpu_info(self):
        """Get CPU vendor and model"""
        try:
            with open("/proc/cpuinfo", "r") as f:
                cpuinfo = f.read()
                if "AuthenticAMD" in cpuinfo:
                    vendor = "AMD"
                elif "GenuineIntel" in cpuinfo:
                    vendor = "Intel"
                else:
                    vendor = "Unknown"
                
                # Get model name
                for line in cpuinfo.split('\n'):
                    if line.startswith("model name"):
                        model = line.split(":")[1].strip()
                        return {"vendor": vendor, "model": model}
                
                return {"vendor": vendor, "model": "Unknown"}
        except:
            return {"vendor": "Unknown", "model": "Unknown"}
    
    def _get_gpu_info(self):
        """Get GPU information from lspci"""
        result = self._run_cmd(["lspci", "-nnk"])
        gpus = []
        
        if result["returncode"] == 0:
            lines = result["stdout"].split('\n')
            for i, line in enumerate(lines):
                if "VGA compatible controller" in line or "3D controller" in line:
                    gpu_info = {
                        "line": line.strip(),
                        "driver": None,
                        "kernel_modules": None
                    }
                    
                    # Check next few lines for driver info
                    for j in range(i+1, min(i+5, len(lines))):
                        if "Kernel driver in use:" in lines[j]:
                            gpu_info["driver"] = lines[j].split(":")[-1].strip()
                        if "Kernel modules:" in lines[j]:
                            gpu_info["kernel_modules"] = lines[j].split(":")[-1].strip()
                    
                    gpus.append(gpu_info)
        
        return gpus
    
    def _get_dmesg(self):
        """Get kernel logs (last 500 lines)"""
        result = self._run_cmd(["dmesg", "-T"], shell=False)
        if result["returncode"] == 0:
            lines = result["stdout"].split('\n')
            # Return last 500 lines to keep it manageable
            return '\n'.join(lines[-500:])
        return result.get("stderr", "Failed to get dmesg")
    
    def _get_libvirt_logs(self, vm_name):
        """Get libvirt logs"""
        logs = {}
        
        # Main libvirt log
        libvirt_log = "/var/log/libvirt/libvirtd.log"
        if os.path.exists(libvirt_log):
            try:
                with open(libvirt_log, "r") as f:
                    lines = f.readlines()
                    logs["libvirtd"] = ''.join(lines[-200:])  # Last 200 lines
            except:
                logs["libvirtd"] = "Failed to read libvirtd.log"
        
        # VM-specific log
        if vm_name:
            vm_log = f"/var/log/libvirt/qemu/{vm_name}.log"
            if os.path.exists(vm_log):
                try:
                    with open(vm_log, "r") as f:
                        lines = f.readlines()
                        logs[f"vm_{vm_name}"] = ''.join(lines[-200:])
                except:
                    logs[f"vm_{vm_name}"] = f"Failed to read {vm_name}.log"
        
        # journalctl for libvirtd
        result = self._run_cmd("journalctl -u libvirtd -n 100 --no-pager", shell=True)
        if result["returncode"] == 0:
            logs["journalctl_libvirtd"] = result["stdout"]
        
        return logs
    
    def _get_gpu_status(self):
        """Get GPU binding and driver status"""
        result = self._run_cmd(["lspci", "-nnk"])
        
        status = {
            "lspci_output": result["stdout"] if result["returncode"] == 0 else result.get("stderr", ""),
            "vfio_bound_devices": [],
            "nvidia_bound_devices": [],
            "gpu_processes": self._get_gpu_processes()
        }
        
        # Check what's bound to vfio-pci
        vfio_driver_path = "/sys/bus/pci/drivers/vfio-pci"
        if os.path.exists(vfio_driver_path):
            try:
                devices = os.listdir(vfio_driver_path)
                status["vfio_bound_devices"] = [d for d in devices if d.startswith("0000:")]
            except:
                pass
        
        # Check what's bound to nvidia
        nvidia_driver_path = "/sys/bus/pci/drivers/nvidia"
        if os.path.exists(nvidia_driver_path):
            try:
                devices = os.listdir(nvidia_driver_path)
                status["nvidia_bound_devices"] = [d for d in devices if d.startswith("0000:")]
            except:
                pass
        
        return status
    
    def _get_gpu_processes(self):
        """Get processes holding GPU devices"""
        result = self._run_cmd(
            "lsof /dev/nvidia* /dev/dri/* /dev/fb0 2>/dev/null", 
            shell=True
        )
        if result["returncode"] == 0:
            return result["stdout"]
        return "No processes found or lsof failed"
    
    def _get_iommu_groups(self):
        """Get IOMMU group information"""
        groups = {}
        iommu_path = "/sys/kernel/iommu_groups"
        
        if not os.path.exists(iommu_path):
            return {"error": "IOMMU groups not found - IOMMU may not be enabled"}
        
        try:
            for group_name in os.listdir(iommu_path):
                group_path = os.path.join(iommu_path, group_name, "devices")
                if os.path.exists(group_path):
                    devices = []
                    for device in os.listdir(group_path):
                        # Get device info from lspci
                        result = self._run_cmd(["lspci", "-nns", device])
                        if result["returncode"] == 0:
                            devices.append(result["stdout"].strip())
                    groups[group_name] = devices
        except Exception as e:
            return {"error": f"Failed to read IOMMU groups: {str(e)}"}
        
        return groups
    
    def _get_module_status(self):
        """Get status of relevant kernel modules"""
        modules = ["vfio", "vfio_pci", "vfio_iommu_type1", "nvidia", "nvidia_modeset", "nvidia_drm"]
        status = {}
        
        result = self._run_cmd(["lsmod"])
        if result["returncode"] == 0:
            lsmod_output = result["stdout"]
            for module in modules:
                if module in lsmod_output:
                    # Extract the line for this module
                    for line in lsmod_output.split('\n'):
                        if line.startswith(module + " "):
                            status[module] = "loaded: " + line
                            break
                else:
                    status[module] = "not loaded"
        
        return status
    
    def _get_service_status(self):
        """Get status of relevant services"""
        services = ["libvirtd", "display-manager"]
        status = {}
        
        for service in services:
            result = self._run_cmd(["systemctl", "status", service])
            status[service] = {
                "active": "active" in result["stdout"].lower(),
                "output": result["stdout"][:500]  # First 500 chars
            }
        
        return status
    
    def _get_grub_config(self):
        """Get GRUB configuration"""
        configs = {}
        
        # Check common GRUB config locations
        grub_files = [
            "/etc/default/grub",
            "/etc/sysconfig/grub",
            "/boot/grub/grub.cfg",
            "/boot/grub2/grub.cfg"
        ]
        
        for grub_file in grub_files:
            if os.path.exists(grub_file):
                try:
                    with open(grub_file, "r") as f:
                        configs[grub_file] = f.read()
                except:
                    configs[grub_file] = "Failed to read"
        
        # Get current kernel command line
        try:
            with open("/proc/cmdline", "r") as f:
                configs["current_cmdline"] = f.read().strip()
        except:
            configs["current_cmdline"] = "Failed to read"
        
        return configs
    
    def _get_vfio_config(self):
        """Get VFIO-related configuration"""
        configs = {}
        
        # Check initramfs configs
        initramfs_files = [
            "/etc/initramfs-tools/modules",
            "/etc/dracut.conf.d/local.conf"
        ]
        
        for config_file in initramfs_files:
            if os.path.exists(config_file):
                try:
                    with open(config_file, "r") as f:
                        configs[config_file] = f.read()
                except:
                    configs[config_file] = "Failed to read"
        
        # Check for hook scripts
        hook_base = "/etc/libvirt/hooks"
        if os.path.exists(hook_base):
            configs["hooks_present"] = True
            configs["hook_dirs"] = []
            
            try:
                for root, dirs, files in os.walk(hook_base):
                    configs["hook_dirs"].append({
                        "path": root,
                        "files": files
                    })
            except:
                configs["hook_dirs"] = "Failed to enumerate"
        else:
            configs["hooks_present"] = False
        
        return configs

    def get_last_error_log(self):
        """Get the most recent error log if it exists"""
        log_files = sorted(self.log_dir.glob("diagnostic_*.json"), reverse=True)
        if log_files:
            with open(log_files[0], "r") as f:
                return json.load(f), log_files[0]
        return None, None