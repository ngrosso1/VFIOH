"""
Deterministic system checks for common VFIO issues
These checks don't require AI and can provide immediate feedback
"""

import os
import subprocess

class SystemChecker:
    def __init__(self):
        self.issues = []
        self.warnings = []
        self.info = []
    
    def run_all_checks(self, diagnostic_data):
        """Run all deterministic checks"""
        self.issues = []
        self.warnings = []
        self.info = []
        
        self._check_iommu_enabled(diagnostic_data)
        self._check_vfio_modules(diagnostic_data)
        self._check_gpu_binding(diagnostic_data)
        self._check_kernel_params(diagnostic_data)
        self._check_libvirt_service(diagnostic_data)
        self._check_hooks_setup(diagnostic_data)
        self._check_gpu_processes(diagnostic_data)
        
        return {
            "issues": self.issues,
            "warnings": self.warnings,
            "info": self.info
        }
    
    def _check_iommu_enabled(self, data):
        """Check if IOMMU is enabled"""
        cmdline = data.get("grub_config", {}).get("current_cmdline", "")
        iommu_groups = data.get("iommu_groups", {})
        
        if "iommu=pt" not in cmdline and "iommu=on" not in cmdline:
            self.issues.append({
                "severity": "high",
                "title": "IOMMU not enabled in kernel parameters",
                "description": "The kernel command line doesn't contain iommu=pt or iommu=on",
                "suggestion": "Add 'iommu=pt' to your kernel parameters (Step 1 should do this)"
            })
        
        cpu_vendor = data.get("system_info", {}).get("cpu", {}).get("vendor", "")
        
        if cpu_vendor == "AMD" and "amd_iommu=on" not in cmdline:
            self.issues.append({
                "severity": "high",
                "title": "AMD IOMMU not enabled",
                "description": "AMD CPU detected but amd_iommu=on not in kernel parameters",
                "suggestion": "Add 'amd_iommu=on' to kernel parameters"
            })
        
        if cpu_vendor == "Intel" and "intel_iommu=on" not in cmdline:
            self.issues.append({
                "severity": "high",
                "title": "Intel IOMMU not enabled",
                "description": "Intel CPU detected but intel_iommu=on not in kernel parameters",
                "suggestion": "Add 'intel_iommu=on' to kernel parameters"
            })
        
        if isinstance(iommu_groups, dict) and "error" in iommu_groups:
            self.issues.append({
                "severity": "critical",
                "title": "IOMMU groups not found",
                "description": iommu_groups["error"],
                "suggestion": "Verify IOMMU is enabled in BIOS/UEFI and kernel parameters are correct"
            })
        elif not iommu_groups or len(iommu_groups) == 0:
            self.warnings.append({
                "title": "No IOMMU groups detected",
                "description": "IOMMU may not be properly enabled or configured"
            })
    
    def _check_vfio_modules(self, data):
        """Check if VFIO modules are loaded"""
        modules = data.get("module_status", {})
        required_modules = ["vfio", "vfio_pci", "vfio_iommu_type1"]
        
        for module in required_modules:
            if modules.get(module, "").startswith("not loaded"):
                self.issues.append({
                    "severity": "high",
                    "title": f"VFIO module {module} not loaded",
                    "description": f"Required module {module} is not currently loaded",
                    "suggestion": f"Try: sudo modprobe {module}"
                })
    
    def _check_gpu_binding(self, data):
        """Check GPU driver binding status"""
        gpu_status = data.get("gpu_status", {})
        vfio_devices = gpu_status.get("vfio_bound_devices", [])
        nvidia_devices = gpu_status.get("nvidia_bound_devices", [])
        
        # Check if GPU is bound to nvidia when it should be bound to vfio
        if nvidia_devices and not vfio_devices:
            self.warnings.append({
                "title": "GPU bound to NVIDIA driver",
                "description": "GPU appears to be bound to nvidia driver, not vfio-pci. This is normal before VM starts.",
                "suggestion": "If VM fails to start, GPU may not be releasing properly"
            })
        
        # Check for processes holding GPU
        gpu_processes = gpu_status.get("gpu_processes", "")
        if gpu_processes and "No processes found" not in gpu_processes:
            self.issues.append({
                "severity": "medium",
                "title": "Processes holding GPU devices",
                "description": "Found processes with open file handles to GPU devices",
                "suggestion": "These processes may prevent GPU passthrough. Check start.sh kills them properly",
                "details": gpu_processes[:500]  # First 500 chars
            })
    
    def _check_kernel_params(self, data):
        """Check kernel parameters are correct"""
        cmdline = data.get("grub_config", {}).get("current_cmdline", "")
        
        # Check for conflicting parameters
        if "nouveau.modeset=1" in cmdline:
            self.warnings.append({
                "title": "Nouveau driver enabled",
                "description": "Open source nouveau driver may conflict with NVIDIA passthrough",
                "suggestion": "Consider adding 'nouveau.modeset=0' or blacklisting nouveau"
            })
        
        self.info.append({
            "title": "Current kernel parameters",
            "description": cmdline
        })
    
    def _check_libvirt_service(self, data):
        """Check libvirt service status"""
        services = data.get("service_status", {})
        libvirtd = services.get("libvirtd", {})
        
        if not libvirtd.get("active", False):
            self.issues.append({
                "severity": "critical",
                "title": "libvirtd service not running",
                "description": "The libvirt daemon is not active",
                "suggestion": "Start it with: sudo systemctl start libvirtd"
            })
    
    def _check_hooks_setup(self, data):
        """Check if libvirt hooks are properly set up"""
        vfio_config = data.get("vfio_config", {})
        
        if not vfio_config.get("hooks_present", False):
            self.warnings.append({
                "title": "Libvirt hooks not found",
                "description": "/etc/libvirt/hooks directory doesn't exist",
                "suggestion": "Hooks are required for GPU binding/unbinding. Run Step 2 to set up hooks"
            })
        else:
            hook_dirs = vfio_config.get("hook_dirs", [])
            vm_name = data.get("vm_name")
            
            if vm_name:
                expected_paths = [
                    f"/etc/libvirt/hooks/qemu.d/{vm_name}/prepare/begin",
                    f"/etc/libvirt/hooks/qemu.d/{vm_name}/release/end"
                ]
                
                found_paths = [h["path"] for h in hook_dirs if isinstance(h, dict)]
                
                for expected in expected_paths:
                    if not any(expected in p for p in found_paths):
                        self.warnings.append({
                            "title": f"Hook directory missing: {expected}",
                            "description": "Expected hook directory not found",
                            "suggestion": "Re-run hook setup in Step 2"
                        })
    
    def _check_gpu_processes(self, data):
        """Check for processes that might interfere"""
        services = data.get("service_status", {})
        dm_status = services.get("display-manager", {})
        
        if dm_status.get("active", False):
            self.info.append({
                "title": "Display manager is running",
                "description": "This is normal. start.sh should stop it before VM starts"
            })
        
        # Check kernel logs for relevant errors
        dmesg = data.get("kernel_logs", "")
        error_patterns = [
            ("vfio-pci.*failed", "VFIO-PCI binding failure"),
            ("device.*busy", "Device busy error"),
            ("nvidia.*failed", "NVIDIA driver error"),
            ("IOMMU.*fault", "IOMMU fault detected")
        ]
        
        for pattern, description in error_patterns:
            if self._search_pattern(pattern, dmesg):
                self.warnings.append({
                    "title": f"Kernel log shows: {description}",
                    "description": f"Pattern '{pattern}' found in dmesg",
                    "suggestion": "Check full diagnostic log for details"
                })
    
    def _search_pattern(self, pattern, text):
        """Simple pattern search (could use regex for more complex patterns)"""
        import re
        return re.search(pattern, text, re.IGNORECASE) is not None