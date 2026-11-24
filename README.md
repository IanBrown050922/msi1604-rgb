# MSI Stealth 16 AI+ keyboard RGB for Linux

Set a solid color, choose an animated preset, or give each of the four keyboard zones its own color. This standalone Python utility uses Linux's built-in HID interface. The keyboard runs the effect after the utility exits.

## Compatibility

- **Laptop** — MSI Stealth 16 AI+ B3WF with the MSI MysticLight MS-1604 controller, USB ID `0DB0:1604`.
- **Tested system** — Ubuntu 26.04.1 LTS on x86-64 with Python 3.14. The script uses only the Python standard library. The live-access code targets x86-64 Linux. The RGB packet format itself is CPU-independent.
- **Device checks** — The utility finds the `/dev/hidrawN` device automatically. It expects USB interface `00` and the HID descriptor seen on the tested controller. It rejects a different descriptor or an ambiguous device match.

Solid white and other steady colors have been tested on the B3WF. The animated presets and the save sequence were checked offline. Persistence across a reboot or power loss has yet to be confirmed. The factory startup effect has not been identified.

## Install on Ubuntu

1. Download the [APT setup package](https://ianbrown050922.github.io/msi1604-rgb/setup/msi1604-rgb-apt-setup_0.1.0_all.deb) from this project’s GitHub Pages site. Save it to your Downloads folder.
2. Open a terminal and run:

   ```sh
   cd "$(xdg-user-dir DOWNLOAD)"
   sudo apt install ./msi1604-rgb-apt-setup_0.1.0_all.deb
   sudo apt update
   sudo apt install msi1604-rgb
   ```

The setup package adds the signed APT source and its public key. The key is scoped to this source. Once installed, future utility versions arrive through your normal Ubuntu updates.

To install without adding a source, download the [standalone utility package](https://ianbrown050922.github.io/msi1604-rgb/apt/msi1604-rgb_0.1.0_amd64.deb) and install it from the download folder with `sudo apt install ./msi1604-rgb_0.1.0_amd64.deb`. Update it by installing a newer package.

## Quick start

```sh
msi1604-rgb inspect
msi1604-rgb color FFFFFF --dry-run
sudo msi1604-rgb color FFFFFF --apply
```

The dry run prints the reports without sending them. Apply may require `sudo` because Linux restricts access to the keyboard’s `/dev/hidrawN` device. Inspection and dry runs work without elevated permissions.

If you previously installed a manual copy, check `command -v msi1604-rgb`. The packaged copy is `/usr/bin/msi1604-rgb`. Move your old `/usr/local/bin/msi1604-rgb` copy aside if it still takes precedence.

To run from a source checkout, use `python3 msi1604.py` in place of `msi1604-rgb` in the examples. The script uses only the Python standard library.

## Uninstall

```sh
sudo apt remove msi1604-rgb
sudo apt purge msi1604-rgb-apt-setup
```

The second command removes the source and key installed by the setup package. Keep the setup package if you want APT to retain access to the archive.

## Commands

| Command | What it does |
| --- | --- |
| `inspect` | Shows the matching device and the report sizes from its cached Linux HID descriptor. Also the default when no command is given. |
| `color RGB` | Sets one steady color across all four zones. |
| `zones RGB RGB RGB RGB` | Sets steady colors for zones 1 through 4 in order. |
| `preset NAME [RGB ...]` | Selects an MSI effect and optionally supplies custom colors. |

Use six hex digits per color, such as `4E0923`. If you include `#`, quote the value in the shell, for example `'#4E0923'`.

All lighting commands default to a dry run. Use `--apply` to send reports. Add `--save` to include the save command once after all four zones. You can combine `--dry-run --save` to preview that sequence.

```sh
sudo msi1604-rgb color 4E0923 --apply
sudo msi1604-rgb zones 4E0923 FF0000 00FF00 0000FF --apply
sudo msi1604-rgb color FFFFFF --apply --save
```

To check persistence, reboot after applying with `--save` and observe the keyboard before running the utility again.

## MSI preset mapping

| Utility preset | Effect in MSI code | Firmware mode | Default |
| --- | --- | --- | --- |
| `off` | `Off` | `0x00` | Lighting off |
| `steady` | `Steady` | `0x01` | Solid white |
| `breathing` | `Breath` | `0x02` | Pulsing white |
| `color-cycle` | `ColorCycle` | `0x03` | MSI rainbow palette |
| `wave` | `Wave` | `0x04` | MSI rainbow palette |
| `rainbow` | `ColorCycle` | `0x03` | Alias for `color-cycle` |

`preset steady 4E0923` builds the same reports as `color 4E0923`. Animated presets accept up to six custom colors in pattern order. Use `--speed slow|medium|fast` for animation speed (default `medium`) and `--direction forward|reverse` for wave direction (default `forward`).

```sh
sudo msi1604-rgb preset breathing 4E0923 --apply
sudo msi1604-rgb preset rainbow --apply
sudo msi1604-rgb preset color-cycle 4E0923 FFFFFF 0000FF --apply
sudo msi1604-rgb preset wave --speed fast --direction reverse --apply
sudo msi1604-rgb preset off --apply
```

## HID reports

Each report is 64 bytes including the report ID. The utility uses the same per-zone order traced in MSI Mystic Light's MS-1604 handler.

1. Write Feature Report `02 01 MASK` with zero padding. Masks `01`, `02`, `04`, and `08` select zones 1–4.
2. Request Feature Report ID `01`.
3. Write Feature Report `02 02 MODE ...` with the selected effect and color data.
4. Request Feature Report ID `01`.
5. Repeat for the remaining zones. If requested, write `02 A0` with zero padding once for the whole keyboard, then request Feature Report ID `01` again.

The effect report contains the mode, the period in hundredths of a second as a two-byte little-endian value, X/Y center bytes, wavelength, wave mode, direction, and color frames. Each frame is one position byte (0–100) followed by red, green, and blue. Custom colors are spaced evenly, with the first color repeated at position 100. The remaining bytes are zero.

For solid white, the effect report starts with the following 18 bytes and ends with 46 zero bytes.

```text
02 02 01 64 00 00 00 0f 01 00 00 ff ff ff 64 ff ff ff
```

For `4E0923`, both `ff ff ff` triplets become `4e 09 23`. Use a dry run to see the complete reports for any command.

The protocol was traced in the `LEDKeeper2.exe` service from [MSI Mystic Light 3.0.38.5](https://liveupdate-2.msi.com/autobios/msicenter/Package/Mystic%20Light_3.0.38.5.exe).

## Build and publish packages

Build a new utility release and sign the archive with the existing release key. Install `apt-utils` and GnuPG on the build machine. Replace the version and fingerprint in these examples.

```sh
./packaging/build-deb 0.1.1 docs/apt
./packaging/build-apt-repo docs/apt YOUR_SIGNING_KEY_FINGERPRINT
```

Build the setup package when first publishing the archive or when its source configuration or public key changes. Use a new setup package version and update the README download link when replacing it.

```sh
./packaging/build-deb 0.1.0 docs/setup --setup
```

The setup build uses the archive’s exported public key in `docs/apt/` and the source configuration in `packaging/msi1604-rgb.sources`. GitHub Pages serves `docs/` from `main`. Commit and push the generated files to publish them. Keep the signing key private.
