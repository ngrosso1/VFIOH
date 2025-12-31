"""
VFIOH Hooks Module
Contains libvirt hook management and GPU passthrough scripts
"""

from .hooks import (
    setup_libvirt_hooks,
    update_start_sh,
    update_revert_sh,
    add_gpu_passthrough_devices,
    get_gpu_pci_ids,
    restart_libvirt_service
)

__all__ = [
    'setup_libvirt_hooks',
    'update_start_sh', 
    'update_revert_sh',
    'add_gpu_passthrough_devices',
    'get_gpu_pci_ids',
    'restart_libvirt_service'
]