"""Compatibility helpers for Windows audio endpoint access."""


def get_endpoint_volume(device):
    """Return IAudioEndpointVolume across old and current pycaw APIs."""
    endpoint_volume = getattr(device, "EndpointVolume", None)
    if endpoint_volume is not None:
        return endpoint_volume

    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import IAudioEndpointVolume

    interface = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return interface.QueryInterface(IAudioEndpointVolume)
