# LawPractice Desktop (Windows)

A Windows app, built with Tauri v2 like the School Management desktop app. When it opens, the user
chooses how to work:

| Mode | Best for | Where the data lives |
| --- | --- | --- |
| **On this computer** | Sole practitioners and small firms on one PC, or offices with unreliable internet | On that PC, in `%APPDATA%\com.lawpractice.desktop` |
| **Connect to my firm's server** | Firms with several users (see `docs/DEPLOYMENT.md`) | On the firm's server; the app is a dedicated window for it |

Every feature (trust accounting, fee notes, reports, two-factor sign-in…) is the same in both modes,
because it's the same LawPractice. In "On this computer" mode the app quietly runs a private copy of
the LawPractice server that only that PC can reach, so no internet connection is needed.

## Getting the installer

Every push to `main` (and to the current development branch) builds the installer on GitHub Actions
(`.github/workflows/desktop.yml`):

1. It runs the full test suite.
2. It freezes the Python backend with PyInstaller and smoke-tests it.
3. It builds the Tauri app.
4. It publishes the installer to the **latest-desktop** release:
   `https://github.com/admiremoyo/lawsoftwareNew/releases/tag/latest-desktop`

Files:
- `LawPractice_<version>_x64-setup.exe` – the normal installer. It installs for the current user, so
  no administrator rights are needed.
- `LawPractice_<version>_x64_en-US.msi` – for IT departments deploying to many PCs.

You can also run the build by hand: **Actions → Desktop app → Run workflow**.

PC requirements: Windows 10 or 11, 64-bit, 4 GB RAM, about 400 MB of disk space plus the firm's
documents. The installer downloads Microsoft WebView2 automatically if the PC doesn't have it (it is
built into Windows 11 and recent Windows 10).

> **Windows SmartScreen.** Until the installer is code-signed, Windows shows "Windows protected your
> PC" the first time. Click **More info → Run anyway**. Before selling widely, buy a code-signing
> certificate (an OV certificate costs roughly US$200–400 a year) so customers don't see this warning.

## Using it

**First start, "On this computer":** the setup wizard asks for the firm's details and creates the first
partner's account, exactly as on a server. Tick *Open this way automatically next time* so the app
opens straight into LawPractice.

**Menu bar**
- **File → Dashboard / Print…**
- **File → Back up now**: writes a backup zip of the database, documents and encryption key.
- **File → Back up to USB or another folder…**: makes a backup and copies it to a USB stick, an
  external drive or a synced folder (OneDrive, Google Drive). **Do this at least weekly; a backup
  that stays on the same PC is lost with the PC.**
- **File → Restore from a backup…**: replaces the data on this PC with a backup. The current data is
  backed up first, so a restore can always be undone.
- **File → Open data and backups folder**
- **File → Switch computer / firm server…**: back to the start screen.
- **View**: back, forward, reload, zoom in and out (handy on small laptop screens).

**Automatic backups:** in "On this computer" mode a backup is made automatically once a day while the app
is open. The last 30 are kept in the `backups` folder.

**Downloads:** fee notes, statements, CSV exports and documents are saved to the PC's *Downloads*
folder and opened with the default program (PDF reader, Excel, Word).

**Moving to a new PC:** on the old PC use *Back up to USB…*. Install LawPractice on the new PC, choose
*On this computer*, complete the setup wizard with any details, then use *File → Restore from a backup…*
and sign in with the original accounts.

**Moving from one PC to a firm server:** export your data as CSV and import it (see `ONBOARDING.md`),
or ask your provider to load the backup's database onto the server.

## Selling the desktop edition

- Offer **"LawPractice Desktop"** to sole practitioners and small firms: a once-off setup fee plus an
  annual licence and support fee, for example. It needs no hosting, so your running costs are close
  to zero.
- Offer **"LawPractice Online"** (the server version) to firms with several staff; the same desktop
  app connects to it, so staff get a proper Windows app either way.
- Upgrading a desktop customer to a server later is a data migration, not a new product.

## For developers

```
desktop/
  backend/server.py               runs Django + waitress on 127.0.0.1, daily backups, backup/restore commands
  backend/lawpractice-server.spec PyInstaller recipe (folder build)
  app/ui/                         start screen (plain HTML/CSS/JS)
  app/src-tauri/src/lib.rs        window, menu, starting/stopping the server, downloads, backups
  app/src-tauri/tauri.conf.json   bundle config (NSIS + MSI, WebView2 bootstrapper)
```

Build and run on your own machine (Linux shown; on Windows use PowerShell equivalents):

```bash
pip install -r requirements.txt pyinstaller
DJANGO_DEBUG=0 DJANGO_SECRET_KEY=build-only-build-only-build-only-build-only-key python manage.py collectstatic --noinput
pyinstaller --noconfirm --distpath desktop/backend/dist --workpath desktop/backend/build desktop/backend/lawpractice-server.spec

cd desktop/app && npm install
LAWPRACTICE_SERVER_BIN=../backend/dist/lawpractice-server/lawpractice-server npm run dev   # run without installing
cp -r ../backend/dist/lawpractice-server/. src-tauri/resources/server/ && npm run build    # make an installer
```

Security notes:
- The built-in server listens on `127.0.0.1` only: other computers on the network can't reach it.
- Each installation generates its own secret key (`secret.key` in the data folder). It is included in
  backups, so restored sessions and password-reset links keep working.
- Only the bundled start screen can call into the desktop app. LawPractice pages, including those
  from a firm server, have no access to the computer.
- The app runs as a single instance, so two copies can never write to the same database.
