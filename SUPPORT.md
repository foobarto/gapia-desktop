# Support

## Current support boundary

The verified hardware profile is VITURE Beast with USB ID `35ca:1211` on
GNOME 50 Wayland. Other VITURE glasses may appear as normal displays, but their
native control capabilities have not yet been verified for Gapia Desktop.

## Getting help

Use the repository issue forms for reproducible Gapia Desktop problems and
feature requests. Before filing a bug, collect:

- hardware model, USB ID, and firmware version;
- OS, GNOME Shell, and Gapia Desktop versions;
- the current configuration with private paths removed;
- expected and actual behavior;
- whether disconnecting and reconnecting restored the display layout; and
- relevant controller logs.

Useful diagnostics include:

```sh
systemctl --user status gapia-display.service
journalctl --user -u gapia-display.service --since today
```

Review logs before posting them. Remove user names, home paths, serial numbers,
application titles, and other personal information.

Use private vulnerability reporting instead of a public support issue for
security or privacy defects. SDK download, licensing, firmware, and hardware
warranty questions must be directed to VITURE.
