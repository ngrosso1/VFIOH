"""
Prompt construction for VFIO troubleshooting
"""

class PromptBuilder:
    def __init__(self):
        self.system_prompt = """You are an expert Linux system administrator specializing in KVM/QEMU virtualization and GPU passthrough with VFIO. Your role is to diagnose issues with single-GPU passthrough setups and provide specific, actionable solutions.

You have deep knowledge of:
- IOMMU configuration (Intel VT-d and AMD-Vi)
- VFIO driver binding and unbinding
- Kernel module management (nvidia, vfio-pci, etc.)
- Libvirt/QEMU virtual machine configuration
- GPU passthrough hook scripts
- Common failure modes and their solutions

When analyzing issues, consider:
1. Whether IOMMU is properly enabled in BIOS and kernel
2. If VFIO modules are loaded correctly
3. Whether the GPU is bound to the correct driver at the right time
4. If processes are holding the GPU and preventing passthrough
5. Hook script execution and timing issues
6. Kernel parameter conflicts
7. Display manager interference

Provide your response in the following JSON format:
{
  "confidence": <number 0-100>,
  "diagnosis": "<brief explanation of the root cause>",
  "recommendations": [
    {
      "description": "<what to do>",
      "command": "<exact command to run, or null if manual action>",
      "explanation": "<why this helps>"
    }
  ]
}

Be specific with commands. Use actual PCI IDs, module names, and file paths when available.
Keep confidence realistic - only use 80-100% if you're certain of the diagnosis.
Prioritize recommendations by impact and safety."""

    def build_diagnostic_prompt(self, formatted_data):
        """Build the main diagnostic prompt"""
        prompt = f"""Please analyze this VFIO GPU passthrough issue and provide diagnosis and recommendations.

SYSTEM DIAGNOSTIC DATA:
{formatted_data}

Based on this information, please:
1. Identify the root cause of the issue with confidence level (0-100%)
2. Provide specific recommendations with exact commands where applicable
3. Explain why each recommendation will help

Remember to respond in JSON format as specified."""

        return prompt
    
    def build_followup_prompt(self, previous_response, new_info):
        """Build a follow-up prompt after user tries a recommendation"""
        prompt = f"""The user tried one of your recommendations. Here's the update:

PREVIOUS ANALYSIS:
{previous_response}

NEW INFORMATION:
{new_info}

Based on this new information, please:
1. Update your diagnosis if needed
2. Provide the next steps or alternative solutions

Respond in the same JSON format."""

        return prompt