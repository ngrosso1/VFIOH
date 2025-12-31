set -x

# Stop display manager
systemctl stop display-manager.service

#Kill any lingering X/Wayland sessions holding the GPU
killall -q Xorg Xwayland gdm-xsession || true

sudo lsof /dev/nvidia* /dev/dri/* /dev/fb0 2>/dev/null \
  | awk 'NR>1 {print $2}' | sort -u | tee /tmp/gpu_pids.txt \
  | xargs -r sudo kill -TERM

sleep 2

sudo lsof /dev/nvidia* /dev/dri/* /dev/fb0 2>/dev/null \
  | awk 'NR>1 {print $2}' | sort -u | xargs -r sudo kill -9

for i in {1..5}; do
    modprobe -r nvidia_drm && break
    sleep 1
done

sudo rmmod nvidia_modeset
sudo rmmod nvidia_uvm
sudo rmmod nvidia

# Unbind VTconsoles
echo 0 > /sys/class/vtconsole/vtcon0/bind
echo 0 > /sys/class/vtconsole/vtcon1/bind

# Unbind EFI-Framebuffer
echo efi-framebuffer.0 > /sys/bus/platform/drivers/efi-framebuffer/unbind

# Avoid a Race condition by waiting
sleep 2

modprobe vfio-pci