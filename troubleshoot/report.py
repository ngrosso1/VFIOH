"""
Human-readable report generation
"""

class ReportGenerator:
    def __init__(self):
        self.RED = '\033[91m'
        self.YELLOW = '\033[93m'
        self.GREEN = '\033[92m'
        self.BLUE = '\033[94m'
        self.RESET = '\033[0m'
    
    def print_diagnostic_summary(self, diagnostic_data, check_results):
        """Print a summary of diagnostic findings"""
        print("\n" + "="*70)
        print(f"{self.BLUE}VFIOH Diagnostic Report{self.RESET}")
        print("="*70)
        
        # System info
        sys_info = diagnostic_data.get("system_info", {})
        print(f"\n{self.GREEN}System Information:{self.RESET}")
        print(f"  Distribution: {sys_info.get('distro', 'unknown')}")
        print(f"  Kernel: {sys_info.get('kernel', 'unknown')}")
        
        cpu = sys_info.get("cpu", {})
        print(f"  CPU: {cpu.get('vendor', 'unknown')} - {cpu.get('model', 'unknown')[:50]}")
        
        gpus = sys_info.get("gpu", [])
        if gpus:
            print(f"  GPU(s):")
            for gpu in gpus:
                print(f"    - {gpu.get('line', 'unknown')[:70]}")
                if gpu.get('driver'):
                    print(f"      Driver: {gpu['driver']}")
        
        # Failed step
        if diagnostic_data.get("failed_step"):
            print(f"\n{self.YELLOW}Failed at:{self.RESET} {diagnostic_data['failed_step']}")
        
        # Check results
        issues = check_results.get("issues", [])
        warnings = check_results.get("warnings", [])
        info = check_results.get("info", [])
        
        if issues:
            print(f"\n{self.RED}â—ï¸  Issues Found ({len(issues)}):{self.RESET}")
            for i, issue in enumerate(issues, 1):
                severity = issue.get("severity", "unknown")
                severity_color = self.RED if severity == "critical" else self.YELLOW
                print(f"\n  {i}. [{severity_color}{severity.upper()}{self.RESET}] {issue['title']}")
                print(f"     {issue['description']}")
                if issue.get("suggestion"):
                    print(f"     {self.GREEN}→{self.RESET} {issue['suggestion']}")
                if issue.get("details"):
                    print(f"     Details: {issue['details'][:200]}...")
        else:
            print(f"\n{self.GREEN}âœ"" No critical issues detected{self.RESET}")
        
        if warnings:
            print(f"\n{self.YELLOW}âš ï¸  Warnings ({len(warnings)}):{self.RESET}")
            for i, warning in enumerate(warnings, 1):
                print(f"\n  {i}. {warning['title']}")
                print(f"     {warning['description']}")
                if warning.get("suggestion"):
                    print(f"     {self.GREEN}→{self.RESET} {warning['suggestion']}")
        
        if info:
            print(f"\n{self.BLUE}ℹï¸  Information:{self.RESET}")
            for item in info[:3]:  # Only show first 3 info items
                print(f"  • {item['title']}")
                if len(item.get('description', '')) < 100:
                    print(f"    {item['description']}")
        
        print("\n" + "="*70)
    
    def print_llm_analysis(self, llm_response):
        """Print LLM analysis results"""
        print("\n" + "="*70)
        print(f"{self.BLUE}AI Analysis{self.RESET}")
        print("="*70)
        
        confidence = llm_response.get("confidence", 0)
        confidence_color = self.GREEN if confidence >= 70 else self.YELLOW if confidence >= 40 else self.RED
        
        print(f"\nConfidence: {confidence_color}{confidence}%{self.RESET}")
        
        diagnosis = llm_response.get("diagnosis", "")
        if diagnosis:
            print(f"\n{self.YELLOW}Diagnosis:{self.RESET}")
            print(f"{diagnosis}\n")
        
        recommendations = llm_response.get("recommendations", [])
        if recommendations:
            print(f"{self.GREEN}Recommendations:{self.RESET}")
            for i, rec in enumerate(recommendations, 1):
                print(f"\n{i}. {rec.get('description', '')}")
                
                command = rec.get('command')
                if command:
                    print(f"   {self.BLUE}Command:{self.RESET} {command}")
                
                explanation = rec.get('explanation')
                if explanation:
                    print(f"   {self.YELLOW}Why:{self.RESET} {explanation}")
        
        print("\n" + "="*70)
    
    def format_for_llm(self, diagnostic_data, check_results):
        """Format diagnostic data for LLM consumption"""
        # Create a concise summary for the LLM
        summary = []
        
        # System context
        sys_info = diagnostic_data.get("system_info", {})
        summary.append(f"System: {sys_info.get('distro', 'unknown')} with {sys_info.get('kernel', 'unknown')}")
        
        cpu = sys_info.get("cpu", {})
        summary.append(f"CPU: {cpu.get('vendor', 'unknown')}")
        
        gpus = sys_info.get("gpu", [])
        if gpus:
            for gpu in gpus:
                summary.append(f"GPU: {gpu.get('line', 'unknown')}")
                if gpu.get('driver'):
                    summary.append(f"  Current driver: {gpu['driver']}")
        
        # Failed step
        if diagnostic_data.get("failed_step"):
            summary.append(f"\nFailed Step: {diagnostic_data['failed_step']}")
        
        # Kernel params
        cmdline = diagnostic_data.get("grub_config", {}).get("current_cmdline", "")
        summary.append(f"\nKernel Parameters: {cmdline}")
        
        # Module status
        modules = diagnostic_data.get("module_status", {})
        summary.append(f"\nModule Status:")
        for mod, status in modules.items():
            summary.append(f"  {mod}: {status}")
        
        # GPU status
        gpu_status = diagnostic_data.get("gpu_status", {})
        summary.append(f"\nGPU Status:")
        summary.append(f"  VFIO-bound devices: {gpu_status.get('vfio_bound_devices', [])}")
        summary.append(f"  NVIDIA-bound devices: {gpu_status.get('nvidia_bound_devices', [])}")
        
        # Issues found by deterministic checks
        issues = check_results.get("issues", [])
        if issues:
            summary.append(f"\nDeterministic Checks Found {len(issues)} Issues:")
            for issue in issues:
                summary.append(f"  - [{issue.get('severity', 'unknown')}] {issue['title']}: {issue['description']}")
        
        warnings = check_results.get("warnings", [])
        if warnings:
            summary.append(f"\nWarnings:")
            for warning in warnings:
                summary.append(f"  - {warning['title']}: {warning['description']}")
        
        # Recent kernel logs (errors and warnings only)
        dmesg = diagnostic_data.get("kernel_logs", "")
        if dmesg:
            error_lines = [line for line in dmesg.split('\n') 
                          if 'error' in line.lower() or 'fail' in line.lower() 
                          or 'vfio' in line.lower() or 'iommu' in line.lower()]
            if error_lines:
                summary.append(f"\nRelevant Kernel Log Entries (last 20):")
                for line in error_lines[-20:]:
                    summary.append(f"  {line}")
        
        # Libvirt logs (errors only)
        libvirt_logs = diagnostic_data.get("libvirt_logs", {})
        for log_name, log_content in libvirt_logs.items():
            if isinstance(log_content, str):
                error_lines = [line for line in log_content.split('\n') 
                              if 'error' in line.lower() or 'fail' in line.lower()]
                if error_lines:
                    summary.append(f"\nLibvirt Log ({log_name}) - Errors (last 10):")
                    for line in error_lines[-10:]:
                        summary.append(f"  {line}")
        
        return '\n'.join(summary)