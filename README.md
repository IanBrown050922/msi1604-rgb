# MSI Stealth 16 AI+ keyboard RGB for Linux

Set a solid color, choose an animated preset, or give each of the four keyboard zones its own color. This standalone Python utility uses Linux's built-in HID interface. The keyboard runs the effect after the utility exits.

## Compatibility

- **Laptop** — MSI Stealth 16 AI+ B3WF with the MSI MysticLight MS-1604 controller, USB ID `0DB0:1604`.
- **Tested system** — Ubuntu 26.04.1 LTS on x86-64 with Python 3.14. The script uses only the Python standard library. The live-access code targets x86-64 Linux. The RGB packet format itself is CPU-independent.
- **Device checks** — The utility finds the `/dev/hidrawN` device automatically. It expects USB interface `00` and the HID descriptor seen on the tested controller. It rejects a different descriptor or an ambiguous device match.

Solid white and other steady colors have been tested on the B3WF. The animated presets and the save sequence were checked offline. Persistence across a reboot or power loss has yet to be confirmed. The factory startup effect has not been identified.

## Install the Ubuntu package

Download the `amd64.deb` package from the project’s [GitHub releases](https://github.com/IanBrown050922/msi1604-rgb/releases) when available. In the download folder, install it with APT. Replace the filename if you downloaded a different version.

```sh
sudo apt install ./msi1604-rgb_0.1.0_amd64.deb
msi1604-rgb --help
```

Install a newer `.deb` with the same command to update. A standalone package does not configure an APT source. If you previously installed a manual copy in `/usr/local/bin`, check `command -v msi1604-rgb`. That copy can take precedence over the packaged command in `/usr/bin`.

## Quick start from source

Download or clone this repository and open a terminal in its folder. No Python packages need to be installed.

```sh
python3 --version
python3 msi1604.py inspect
python3 msi1604.py color FFFFFF --dry-run
```

The dry run checks the device and prints the reports it would send. To apply white:

```sh
sudo python3 msi1604.py color FFFFFF --apply
```

If Linux reports **Permission denied** for `/dev/hidrawN`, use `sudo` for the apply command as shown. This requires an account allowed to use `sudo`. Inspection and dry runs need no elevated permissions.

## Optional system-wide install

From the repository folder, install the command into `/usr/local/bin`:

```sh
sudo install -m 755 msi1604.py /usr/local/bin/msi1604-rgb
```

You can then run it from any directory:

```sh
msi1604-rgb --help
msi1604-rgb preset --help
sudo msi1604-rgb color FFFFFF --apply
```

Repeat the install command after updating the script to refresh the installed copy.

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
sudo python3 msi1604.py color 4E0923 --apply
sudo python3 msi1604.py zones 4E0923 FF0000 00FF00 0000FF --apply
sudo python3 msi1604.py color FFFFFF --apply --save
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
sudo python3 msi1604.py preset breathing 4E0923 --apply
sudo python3 msi1604.py preset rainbow --apply
sudo python3 msi1604.py preset color-cycle 4E0923 FFFFFF 0000FF --apply
sudo python3 msi1604.py preset wave --speed fast --direction reverse --apply
sudo python3 msi1604.py preset off --apply
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

From the repository folder on Ubuntu or Debian, build a package with the release version:

```sh
./packaging/build-deb 0.1.0 dist
```

Upload the resulting `.deb` as a GitHub release asset. To provide updates through APT, use `apt-utils` and GnuPG to create a signed package index. Use an archive signing key you control and supply its fingerprint:

```sh
./packaging/build-apt-repo dist YOUR_SIGNING_KEY_FINGERPRINT
```

Publish the contents of `dist` together at a stable HTTPS URL. Keep the signing key private. Tell users the HTTPS URL and the key fingerprint so they can verify the public key and configure the source.

After verifying the key from the hosted archive, users can install it as `/etc/apt/keyrings/msi1604-rgb.asc` and create `/etc/apt/sources.list.d/msi1604-rgb.sources` with the following fields, replacing the example URL:

```text
Types: deb
URIs: https://example.org/msi1604-rgb/apt/
Suites: ./
Architectures: amd64
Signed-By: /etc/apt/keyrings/msi1604-rgb.asc
```

Then `sudo apt update` and `sudo apt install msi1604-rgb` install the utility. Subsequent releases can be installed through normal APT upgrades.
