# Setting up the measurement database on a Windows PC

This document walks you through turning one Windows PC into the computer that keeps every measurement:
the database that lists them, the folder that holds their data files, and a small web server that lets
any other computer on the network look at them. In the project's documents this PC is called `qdt-db`.
The computer that drives the instruments and takes the measurements is called the measurement PC; in
the first run-through it is a laptop running the simulated instruments.

You do not need to have used PostgreSQL before. Each step says what you are doing, what it changes on
the computer, and how to check that it worked. Expect the whole setup to take an afternoon, most of it
in Parts 1–3. Nothing here touches the lab network; the first run is on your own two machines, and the
same steps are repeated unchanged on the lab's database PC later (ADR 0080).

Every name, address and password in this file is a placeholder, shown in angle brackets like
`<admin password>`. Real ones stay on your machines and never go into this repository or into a GitHub
issue (project rule 7). Where a placeholder is a path, you may keep the suggested one.

## What you are building

Three pieces of software run on `qdt-db` when you are done:

1. **PostgreSQL**, a database program that runs in the background as a Windows service. It stores the
   *catalogue* of measurements: for each one, which device and stand it was taken on, when, with what
   settings, and the name and checksum of its data file. It does not store the measured numbers themselves.
2. **A shared folder** that holds the data files (one HDF5 file per measurement). The measurement PC
   writes into it over the network; the web server below reads from it; nobody else touches it.
3. **The read server**, `python -m qdt_server --read-only`, a program from this repository. It answers
   questions about the catalogue over HTTP, hands out data files, and serves the Flight Deck web page.
   It connects to PostgreSQL with a read-only account, so it cannot change anything, and it does not know
   any instrument exists.

The measurement PC keeps running exactly as before, with two extra settings that tell it where the
database and the shared folder are. After every measurement it copies the record to `qdt-db`. If
`qdt-db` is switched off, the record waits on the measurement PC and is copied the next time anything
succeeds (ADR 0080).

```
measurement PC (laptop)                       qdt-db (desktop)
┌───────────────────────────┐                 ┌────────────────────────────────────┐
│ python -m qdt_server      │  SQL, port 5432 │ PostgreSQL service                 │
│   (the stand server)      │ ──────────────▶ │   database "qdt"                   │
│   local cache + data files│  file sharing   │ shared folder  C:\qdt\payloads     │
│                           │ ──────────────▶ │                                    │
│ Flight Deck in a browser  │                 │ python -m qdt_server --read-only   │
└───────────────────────────┘                 │   http://qdt-db:8700  (+ 8765)     │
                                              └────────────────────────────────────┘
any other computer ──── browser or Python script ────▶ http://qdt-db:8700, or SQL as a reader
```

Three database accounts are created, each allowed to do only its job: `qdt_admin` creates the tables and
is used once; `qdt_writer` is what the measurement PC uses to add records; `qdt_reader` is what the read
server and your scripts use, and it can only read. This way a mistake in a script, or a browser on the
wrong desk, cannot change or delete a measurement (ADR 0074).

## Before you start

You need:

- The Windows PC that will be `qdt-db`, with an account that is an administrator on it. It should be
  set never to sleep (Settings → System → Power → "Never" for sleep when plugged in), because a sleeping
  database is an absent one.
- A second computer on the same home or lab network to be the measurement PC. For the first run it only
  needs this repository and Python; no instruments.
- Both computers able to see each other on the network. The easiest test is to find `qdt-db`'s address
  (Part 3, step 5) and `ping` it from the laptop.
- On both machines: this repository cloned, `uv` installed (https://docs.astral.sh/uv/), and
  `uv sync --all-packages --all-extras` run once inside the clone. On `qdt-db` you also need Node.js
  20 or newer for Part 6, because the Flight Deck page is built there.

**Where things live.** The document names a handful of folders and files on `qdt-db` and on the laptop.
Every one of them is your choice; the paths below are only what the examples use, so that they read
consistently. If yours differ, substitute them wherever they appear. The right-hand column says what
constrains the choice.

| In the examples | What it is | Rules |
|---|---|---|
| `C:\qdt\repo` (Windows), `~/qdt/repo` (Mac) | This repository, cloned | Anywhere on a local disk. |
| `C:\qdt\payloads` on `qdt-db` | The folder that holds every measurement's data file; shared as `qdt-payloads` (Part 5) | The largest disk the PC has. Grows for ever; include it in backups (Part 9). |
| `C:\qdt\read-server` on `qdt-db` | The read server's scratch folder, named by `--root` (Part 6) | Small. On a local disk, outside the repository, and **not inside** `C:\qdt\payloads`, because the program creates a `payloads` subfolder of its own in it. |
| `C:\qdt\read-server.ps1` on `qdt-db` | The start-up script you write in Part 6, step 2 | Anywhere **outside the repository**, because it holds the reader password. Steps 3 and 5 of Part 6 must name the same path. |
| `C:\qdt\backup` and `C:\qdt\backup.ps1` on `qdt-db` | The nightly dumps and payload mirror, and the script that makes them (Part 9) | The folder on a different physical disk from the database and the payloads, if the PC has one. The script anywhere outside the repository (it holds a password). |
| `~/qdt-payloads` on a Mac laptop | The mount point for the share (Part 5, step 5) | An empty folder in your home directory; the script creates it. |

Keeping them side by side under one folder (`C:\qdt\…`), as the examples do, makes them easy to find; it
is not required.

**Which computer, which command line.** `qdt-db` is a Windows PC in this document, and every command
you type on it is for **PowerShell**: open it from the Start menu, and where a step says "as
administrator", right-click it and choose *Run as administrator*. (Windows also has *Command Prompt*,
which looks alike but sets variables differently; do not use it here.) The measurement PC may be a
Windows laptop or a Mac. Wherever a laptop command differs, it is given twice, marked **Windows laptop**
(PowerShell) and **Mac laptop** (the *Terminal* app, in Applications → Utilities). Commands that are the
same on both, such as `uv run …`, are given once.

**If the two machines talk over Tailscale.** Tailscale is a VPN that gives each of your devices a fixed
address of the form `100.x.y.z` and a name, and encrypts everything between them, whether they are in the
same room or in different cities. If both machines run it, three things in this document become simpler,
and they are called out in boxes like this one where they occur: the address range in Part 3 is
Tailscale's instead of your home network's, the name `qdt-db` comes free from Tailscale instead of a
hosts file, and you never have to open anything on your home network at all. The connection is already
encrypted, so the project's note about needing TLS once a client is off the local network is satisfied.

## Part 1 — Install PostgreSQL

**What this does.** It puts the database program on the PC and registers it as a Windows service, which is
a program that Windows starts at boot and keeps running whether or not anyone is logged in.

1. Download the Windows installer from https://www.postgresql.org/download/windows/ (the link goes to
   EnterpriseDB, who build the official Windows package). Choose the newest version 17 release.

2. Run the installer. When it asks which components to install, keep **PostgreSQL Server** and **Command
   Line Tools** ticked. **pgAdmin 4** is a graphical administration program; it is harmless but you will not
   need it here. Untick **Stack Builder**; it only offers downloads of extras.

3. Accept the default *data directory*, `C:\Program Files\PostgreSQL\17\data`. This folder is where the
   database keeps everything it stores, and where two configuration files you will edit in Part 3 live.

4. When asked for a password, you are setting the password of the database's built-in superuser, an
   account named `postgres` that can do anything inside the database. Choose a strong one and keep it in
   your password manager as "postgres superuser on qdt-db". You will use it in Parts 2 and 9 only.

5. Accept port **5432** (the number other computers will connect to) and the default locale.

**What changed on the PC.** A Windows service named `postgresql-x64-17` now runs in the background and
starts with the machine. (The number is the PostgreSQL version you installed; 17 and 18 are both current,
and whichever you have appears in the service name and the program folder wherever this document says 17.)
The program files are in `C:\Program Files\PostgreSQL\17\bin`, including `psql`,
the command-line tool you will use to talk to the database. The database itself contains one account
(`postgres`) and some empty default databases, and it accepts connections only from this same PC.

**Check it.** Press the Windows key, type `services`, open *Services*, and find *postgresql-x64-17* (or *-18*): its
Status should be *Running* and its Startup Type *Automatic*. Then open *SQL Shell (psql)* from the Start
menu. It asks for server, database, port and username one after another; press Enter to accept each
default, then type the superuser password. You should see the prompt `postgres=#`. Type

```sql
SELECT version();
```

and press Enter: it prints a line beginning `PostgreSQL 17`. Type `\q` and Enter to leave.

6. Make `psql` available from any PowerShell window, because the remaining parts type commands there.
   Press the Windows key, type `environment`, open *Edit the system environment variables*, click
   *Environment Variables…*, select *Path* under *System variables*, click *Edit…*, then *New*, and add
   `C:\Program Files\PostgreSQL\17\bin`. Click OK in every dialog. **Check it:** open a *new* PowerShell
   window (existing ones do not see the change) and type `psql --version`; it prints `psql (PostgreSQL) 17.x`.

## Part 2 — Create the database and its three accounts

**What this does.** A PostgreSQL server can hold several independent databases. You create one, named
`qdt`, for the measurements, and three accounts (PostgreSQL calls them *roles*) that may connect to it,
each with its own permissions. The permissions are written in the file `deploy\qdt-db\roles.sql` in this
repository, so you do not have to type them.

1. Choose three passwords, one per account, and store them in your password manager as
   "qdt_admin", "qdt_writer" and "qdt_reader" on qdt-db. Use letters and digits only: these passwords
   will later be written inside a connection address, where characters such as `@`, `:`, `/` and `%` have
   meanings of their own and would have to be escaped.

2. Open PowerShell and create the database. The command connects to the server as the superuser (`-U
   postgres`), to the default database that always exists (`-d postgres`), and runs one SQL statement
   (`-c`). It asks for the superuser password.

   ```powershell
   psql -U postgres -d postgres -c "CREATE DATABASE qdt;"
   ```

   It answers `CREATE DATABASE`.

3. Create the three accounts by running the project's SQL file. In the command below, `-v` passes a value
   into the file (the file refers to them as `:db`, `:'admin_pw'` and so on), and `-f` names the file to
   run. Replace the three placeholders with the passwords you chose, keeping the single quotes. If you
   cloned the repository elsewhere, adjust the path.

   ```powershell
   cd C:\qdt\repo
   psql -U postgres -d postgres -v db=qdt -v admin_pw='<admin password>' -v writer_pw='<writer password>' -v reader_pw='<reader password>' -f deploy\qdt-db\roles.sql
   ```

   It asks for the superuser password, possibly twice (the file reconnects to the new database halfway
   through), and prints a line for each statement: `CREATE ROLE` three times, then `GRANT` and `ALTER
   DEFAULT PRIVILEGES` lines. Any line beginning `ERROR` means the step did not complete; the most likely
   cause is running the file a second time, because the accounts then already exist.

**What changed.** The server now has a database named `qdt` (still empty: no tables yet) and three
accounts. `qdt_admin` may create tables in it. `qdt_writer` may read and add rows to any table the admin
creates, but never change or delete a row, which matches how the project treats measurements: they are
only ever added (ADR 0026). `qdt_reader` may only read.

**Check it.** List the databases and the accounts:

```powershell
psql -U postgres -d postgres -c "\l"
psql -U postgres -d postgres -c "\du"
```

The first shows `qdt` in the list; the second shows `qdt_admin`, `qdt_writer` and `qdt_reader`. Now connect
as the reader to prove the account works. `-h 127.0.0.1` means "over the network, to this same machine",
which is how every other program will connect:

```powershell
psql -U qdt_reader -h 127.0.0.1 -d qdt -c "SELECT current_user;"
```

It asks for the reader password and prints `qdt_reader`.

## Part 3 — Let other computers connect

**What this does.** Out of the box PostgreSQL listens only on the PC it runs on, and Windows Firewall
blocks incoming connections. Two configuration files decide who may connect: `postgresql.conf` says which
network interfaces the server listens on, and `pg_hba.conf` ("host-based authentication") says which
accounts may connect to which database from which addresses, and how they must prove who they are. You
open both to the computers on your network and no further, then open the firewall for the same.

1. Find your network's address range, so the rules admit only it. Run `ipconfig` in PowerShell and look at
   the adapter you use (Ethernet or Wi-Fi): note the *IPv4 Address*, for example `192.168.1.23`, and the
   *Subnet Mask*, for example `255.255.255.0`. A mask of `255.255.255.0` means every computer on your
   network shares the first three numbers; the range is then written `192.168.1.0/24`. Write your range
   down; it is `<lab-subnet>` in the rest of this document. Also write down the IPv4 address itself: it is
   how the laptop will find this PC in step 5.

   **Over Tailscale**, skip `ipconfig`. Every Tailscale device gets an address from one fixed block,
   `100.64.0.0/10`, so that is your `<lab-subnet>`, and the address to write down is `qdt-db`'s Tailscale
   address (shown in the Tailscale app, or by `tailscale ip -4`). The number after the slash counts how
   many *bits* at the front of the address are fixed, not how many of the four numbers: each number is 8
   bits, so `/24` fixes the first three numbers, while `/10` fixes the first number and 2 bits of the
   second, which pins the second number to the quarter from 64 to 127. So `100.64.0.0/10` means "first
   number 100, second number 64 to 127, the rest anything": it covers a laptop at `100.123.…` and a
   desktop at `100.70.…` alike, and any device you add to the tailnet later. (To admit one laptop only,
   use its own address followed by `/32`, which means "exactly this address".)

2. Open the data directory's configuration files with administrator rights. Open Notepad as administrator
   (Start menu, type *Notepad*, right-click, *Run as administrator*), then File → Open, navigate to
   `C:\Program Files\PostgreSQL\17\data`, and change the file type dropdown to *All files*.

3. In `postgresql.conf`, use Ctrl-F to find the line

   ```
   #listen_addresses = 'localhost'
   ```

   The `#` at the start marks the line as a comment, meaning the setting is at its default. Change it to

   ```
   listen_addresses = '*'
   ```

   which means "listen on every network interface this PC has". Save the file. (Who may actually connect is
   decided by the next file and the firewall; this line alone opens nothing to anyone.)

4. In `pg_hba.conf`, scroll to the bottom. Each line is a rule with five columns: the connection type,
   the database, the account, the address range it applies to, and the authentication method. The
   existing rules already allow connections from this PC itself, which is why Part 2's checks worked. Add
   two lines, with your range in place of the placeholder:

   ```
   host    qdt    qdt_writer    <lab-subnet>    scram-sha-256
   host    qdt    qdt_reader    <lab-subnet>    scram-sha-256
   ```

   They read: "a network connection to database `qdt` as `qdt_writer` (or `qdt_reader`) from any address
   in this range is allowed if it presents the right password" (`scram-sha-256` is the password method).
   There is deliberately no line for `qdt_admin` or `postgres` from the network: those accounts are used
   only at this PC. Never write `0.0.0.0/0` here; it would mean "from anywhere". Save the file.

5. Restart the service so it reads the two files: in *Services*, right-click *postgresql-x64-17* (or *-18*) and
   choose *Restart*. **Check it** from this PC, connecting to its own network address instead of
   `127.0.0.1` (use the IPv4 address from step 1):

   ```powershell
   psql -U qdt_reader -h <qdt-db's IPv4 address> -d qdt -c "SELECT 1;"
   ```

   It asks for the reader password and prints a small table containing `1`. If instead it says `no
   pg_hba.conf entry for host`, the address range in step 4 does not include this address; if it says
   `could not connect`, step 3 did not take effect or the service was not restarted.

6. Open Windows Firewall for port 5432, from your network only. In PowerShell **as administrator**:

   ```powershell
   New-NetFirewallRule -DisplayName "qdt-db PostgreSQL" -Direction Inbound -Protocol TCP -LocalPort 5432 -RemoteAddress <lab-subnet> -Action Allow
   ```

   This creates one inbound rule (`-Direction Inbound`) that allows (`-Action Allow`) TCP connections to
   port 5432 (`-LocalPort`) when they come from your address range (`-RemoteAddress`). You can see and
   delete it later under *Windows Defender Firewall with Advanced Security → Inbound Rules*.

   **Over Tailscale**, use `-RemoteAddress 100.64.0.0/10` and add `-InterfaceAlias Tailscale`, which ties
   the rule to the Tailscale network adapter so it can never match traffic arriving any other way (if
   `Get-NetAdapter` shows the adapter under a different name, use that). Do the same for the rule in Part
   6, step 4.

7. Give the PC a name the laptop can use. The project's documents call it `qdt-db`.

   **Over Tailscale** there is nothing to do: Tailscale's MagicDNS already lets the laptop reach the desktop
   by its machine name (as shown in the Tailscale app, or in full as `<name>.<your tailnet>.ts.net`). Use
   that name wherever this document says `qdt-db`. **Check it:** on the laptop, `ping <name>` answers
   from the desktop's `100.x.y.z` address (press Ctrl-C to stop it).

   Otherwise, if your network has no DNS that knows the name, add one line to the laptop's *hosts* file,
   which maps a name to an address on that laptop only.

   *Windows laptop:* open Notepad as administrator, open `C:\Windows\System32\drivers\etc\hosts` (set the
   file-type dropdown to *All files*), add at the end, and save:

   ```
   <qdt-db's IPv4 address>    qdt-db
   ```

   *Mac laptop:* in Terminal, `sudo nano /etc/hosts`; it asks for your Mac password and opens the file in
   a small editor. Move to the end with the arrow keys, add the same line, press Ctrl-O then Enter to
   save, and Ctrl-X to leave. If the name does not work straight away, clear the Mac's name cache with
   `sudo dscacheutil -flushcache; sudo killall -HUP mDNSResponder`.

   On either, **check it** with `ping qdt-db`. For a home network where the desktop's address may change
   when the router restarts, either reserve the address in the router's settings (often called "DHCP
   reservation") or simply use the IPv4 address in place of `qdt-db` everywhere below.

**Check it from the laptop.** Ask whether port 5432 on `qdt-db` accepts a connection.

*Windows laptop:*

```powershell
Test-NetConnection qdt-db -Port 5432
```

The last line should read `TcpTestSucceeded : True`.

*Mac laptop:*

```
nc -vz qdt-db 5432
```

It prints `Connection to qdt-db port 5432 [tcp/postgresql] succeeded!`.

If the test fails, the firewall rule or the address range is wrong, or the two machines are not on the
same network. If the laptop has PostgreSQL's command-line tools (it does not need them otherwise; on a
Mac `brew install libpq` provides `psql`), `psql -U qdt_reader -h qdt-db -d qdt -c "SELECT 1;"` should
then work as it did in step 5.

## Part 4 — Create the tables

**What this does.** The database `qdt` is still an empty container. The project creates its own tables
(records, devices, analysis results and so on) with one command, run as `qdt_admin`, so that the tables
belong to the admin account and the permissions from Part 2 apply to them. The same command checks that
the tables match the version of the software, and refuses to continue if an older server meets a newer
client, which protects you from silent mismatches (ADR 0026).

1. The project's programs find the database through one setting, an environment variable named
   `QDT_REGISTRY_DSN`. Its value is a connection address in this shape:

   ```
   postgresql+psycopg://<account>:<password>@<host>:5432/qdt
   ```

   `postgresql+psycopg` says which database driver to use, then the account and its password, then the
   machine and port, then the database name. For this one-time step the account is `qdt_admin` and the
   host is `127.0.0.1`, this PC itself. In PowerShell a variable set with `$env:` lasts until that window
   is closed, which is what you want for a one-time command:

   ```powershell
   cd C:\qdt\repo
   $env:QDT_REGISTRY_DSN = "postgresql+psycopg://qdt_admin:<admin password>@127.0.0.1:5432/qdt"
   uv run python -m qdt_registry init
   ```

   It prints `server ready, ddl_version 3` (the number is the current table-layout version). Close the
   PowerShell window afterwards so the admin password is not left in a live variable.

**What changed.** The database `qdt` now contains the project's tables, all empty.

**Check it.** `psql -U postgres -d qdt -c "\dt"` lists the tables; you should see names such as `devices`,
`objects`, `records`, `analysis_results`, `tuning_outcomes` and `registry_meta`. Running the `init`
command a second time is harmless: it finds the tables already there and prints the same line.

## Part 5 — The folder for the data files, shared with the measurement PC

**What this does.** The numbers a measurement produces live in a file, not in the database (the database
row holds the file's name and checksum). The measurement PC must be able to put files into a folder on
`qdt-db`, so you create the folder, create a Windows account whose only purpose is to write into it, and
share the folder on the network for that account. Windows file sharing is also called SMB.

1. Create the folder. If this PC has a second, larger disk, put the folder there instead of on `C:`, and
   use that path wherever `C:\qdt\payloads` appears below.

   ```powershell
   New-Item -ItemType Directory -Path C:\qdt\payloads
   ```

2. Create a local Windows user for the measurement PC to connect as, in PowerShell **as administrator**.
   Using a separate account, rather than your own, means the laptop never holds your login, and you can
   change this one password without touching anything else. Choose a password and store it as
   "qdtshare on qdt-db".

   ```powershell
   New-LocalUser -Name qdtshare -Password (Read-Host -AsSecureString "Password for qdtshare") -PasswordNeverExpires -UserMayNotChangePassword
   ```

   It prompts for the password rather than taking it on the command line, so it is not left in the
   window's history. `-PasswordNeverExpires` matters: an expired password would stop the laptop's copies
   silently one day.

3. Share the folder for that account, still as administrator. Sharing has two gates: the *share
   permission* (who may reach the folder over the network) and the *folder permission* (who may write in
   it). The first command sets both for `qdtshare`; the second gives the folder permission explicitly,
   because `New-SmbShare` does not always add it.

   ```powershell
   New-SmbShare -Name qdt-payloads -Path C:\qdt\payloads -FullAccess qdtshare
   icacls C:\qdt\payloads /grant "qdtshare:(OI)(CI)M"
   ```

   `(OI)(CI)` means the permission applies to files and subfolders created later too, and `M` is "modify":
   create, write and rename, which is what the measurement PC needs. It writes each file under a temporary
   name and renames it when complete, so a copy that is interrupted never leaves a half file under its
   final name.

4. Windows allows file sharing only when the network is classed as *Private*. Open Settings → Network &
   internet, click your connection, and make sure *Network profile type* is *Private network*. (On a
   *Public* network Windows blocks sharing regardless of the steps above.)

   **Over Tailscale**, Windows usually classes the Tailscale adapter as *Public*, so file sharing over it
   is blocked by the built-in firewall rules even though the folder is shared. Rather than reclassifying
   the adapter, add one explicit rule for file sharing's port, 445, from Tailscale only, in PowerShell as
   administrator:

   ```powershell
   New-NetFirewallRule -DisplayName "qdt-db share over Tailscale" -Direction Inbound -Protocol TCP -LocalPort 445 -RemoteAddress 100.64.0.0/10 -InterfaceAlias Tailscale -Action Allow
   ```

**What changed.** The PC has a new local user `qdtshare`, a folder `C:\qdt\payloads`, and a network share
named `qdt-payloads` that only `qdtshare` can reach. Other computers see it as `\\qdt-db\qdt-payloads`.

**Check it from the laptop.**

*Windows laptop:* open File Explorer, type `\\qdt-db\qdt-payloads` in the address bar and press Enter.
Windows asks for a username and password: enter `qdt-db\qdtshare` and the share password, and tick
*Remember my credentials*. The folder opens, empty.

*Mac laptop:* in Finder press Cmd-K (Go → Connect to Server), enter `smb://qdt-db/qdt-payloads` and click
Connect. Choose *Registered User*, enter `qdtshare` and the share password, and tick *Remember this
password in my keychain*. The folder opens, empty. Finder has also stored the share password in your
keychain, which step 5 relies on; the folder it opened is temporary (it disappears at logout) and step 5
gives the share a permanent place.

On either, create a new text file in the folder, then delete it: both must work.

5. Make the share available to the measurement PC's server, which runs without a file window open, and
   make it come back after a reboot.

   *Windows laptop:* store the credentials in Windows, in PowerShell as the user who will run the server:

   ```powershell
   cmdkey /add:qdt-db /user:qdt-db\qdtshare /pass:<share password>
   ```

   **Check it:** in a new PowerShell window, `dir \\qdt-db\qdt-payloads` lists the (empty) folder without
   asking for a password. You will give the measurement PC this path, `\\qdt-db\qdt-payloads`, in Part 7;
   there is no need to map it to a drive letter.

   *Mac laptop:* the keychain entry from the check above is the stored credential. Do **not** add the share
   to System Settings' *Login Items*: on current macOS a network folder there either does nothing at login
   or stops at a password dialog that nobody is there to confirm. Instead, a small script mounts the share
   when you log in, without Finder, and keeps trying for five minutes while the network (or Tailscale)
   comes up. It attaches the share to an empty folder in your home directory, `~/qdt-payloads` (a *mount
   point*; `~` is your home folder, and a mount point under `/Volumes` would need administrator rights),
   and takes the password from the keychain entry Finder saved, so the password is written in no file.

   The project's script `deploy/qdt-db/mac-payload-mount.sh` sets all of this up. First eject the folder
   Finder opened in the check above (click ⏏ next to `qdt-payloads` in Finder's sidebar), so that the test
   at the end is real. Then, in Terminal:

   ```sh
   cd ~/qdt/repo
   bash deploy/qdt-db/mac-payload-mount.sh
   ```

   It prints one line per step. Partway through, a dialog asks whether `security` may read the share
   password from the keychain: click **Always Allow**, not *Allow*, which would ask again at every login
   with nobody there to answer. The script is safe to run again at any time; every step checks before it
   changes anything. What it does:

   1. Checks that the keychain entry from the Finder check exists, and stops with instructions if not.
   2. Creates the mount point `~/qdt-payloads`. It stays empty; while the share is mounted, looking inside
      shows the share. The folder is made read-only, which matters: if the share were ever not mounted, the
      measurement PC would otherwise write its files into this local folder and believe they had arrived.
      Read-only, the copy fails instead and the record waits in the local cache, as it should (while the
      share is mounted, the share's own permissions apply and writing works). The folder is also *locked*,
      the flag Finder shows as a padlock, so it cannot be moved, renamed or deleted by accident.
   3. Writes the mount script, `~/Library/Scripts/mount-qdt-payloads.sh`, which mounts the share and keeps
      trying for five minutes, and records what it did in `~/Library/Logs/mount-qdt-payloads.log`.
   4. Writes and loads a *Launch Agent*, `~/Library/LaunchAgents/com.qdt.mount-payloads.plist`: a small
      file that tells macOS to run the mount script when you log in.
   5. Runs the mount script once now, and prints the path to give the measurement PC in Part 7.

   If you reach `qdt-db` over Tailscale and the short name does not work on the Mac, run it with the name
   Finder used instead: `QDT_DB_HOST=<Tailscale address or full ….ts.net name> bash deploy/qdt-db/mac-payload-mount.sh`.

   **Check it:** `bash deploy/qdt-db/mac-payload-mount.sh check` says whether the share is mounted, whether
   the Launch Agent is loaded, what the last mount attempt logged, and (when unmounted) whether the folder
   refuses writes. Run it now; then the test that counts: log out and in again, wait a minute, and run it
   again. No dialog should have appeared. To undo everything the script did,
   `bash deploy/qdt-db/mac-payload-mount.sh uninstall`.

   **Over Tailscale**, Tailscale itself must start at login, or the Mac cannot find `qdt-db`: tick *Start at
   login* in the Tailscale menu-bar icon's settings, and in System Settings → General → Login Items make
   sure Tailscale is listed and its *Allow in the Background* toggle is on. (If you remove or change entries
   in that list while setting up, check Tailscale's is still there.)

   You will give the measurement PC this path, `/Users/<your Mac username>/qdt-payloads`, in Part 7
   (`whoami` prints the username; the script prints the full path). `bash deploy/qdt-db/mac-payload-mount.sh check`
   before a session is a good habit.

## Part 6 — The read server, started with the PC

**What this does.** The read server is a program from this repository that other computers talk to over
the network. It does three things: it answers questions about the catalogue (for example "list the
records"), it hands out a measurement's data file on request, and it serves the Flight Deck web page so
that a browser on any desk can look at measurements. It connects to the database as `qdt_reader`, so it
cannot change anything, and it holds no instrument. You first build the web page, then run the server
by hand to see it work, then make Windows start it at boot.

1. Build the Flight Deck web page once. Node.js must be installed (https://nodejs.org, version 20 or
   newer). `corepack` comes with Node.js and provides the exact version of the `pnpm` package manager the
   project pins; on Windows it is always called as `corepack pnpm` (issue #114). In PowerShell:

   ```powershell
   corepack enable
   cd C:\qdt\repo\apps\flightdeck
   corepack pnpm install --frozen-lockfile
   corepack pnpm build
   ```

   The last command ends with `✓ built in …` and creates the folder `apps\flightdeck\dist`, which is the
   finished web page. Rebuild it the same way whenever you update the repository.

2. Write the script that starts the read server. Nothing generates this file: you type it, now, as a new
   text file of four lines. It can live anywhere outside the repository (it will hold the reader password);
   the examples call it `C:\qdt\read-server.ps1`, and steps 3 and 5 refer to it by that full path, so use
   yours there too. Create it from PowerShell, so that the file gets exactly that name (Notepad started
   from the Start menu silently adds `.txt`, which File Explorer then hides):

   ```powershell
   notepad C:\qdt\read-server.ps1
   ```

   Notepad asks whether to create the file; say yes, paste the content below, save, and close. Replace
   the reader password and, if yours differ, the three paths (see *Where things live*):

   ```powershell
   $env:QDT_REGISTRY_DSN = "postgresql+psycopg://qdt_reader:<reader password>@127.0.0.1:5432/qdt"
   $env:QDT_PAYLOAD_STORE = "C:\qdt\payloads"
   Set-Location C:\qdt\repo
   uv run python -m qdt_server --read-only --host 0.0.0.0 --port 8700 --stream-port 8765 --ui apps\flightdeck\dist --root C:\qdt\read-server
   ```

   Line by line: the first tells the server where the database is and which account to use; the second
   tells it where the data files are (the folder from Part 5, reached locally, not through the share);
   the third moves into the repository so the program and the web page are found. The last line starts
   the read server itself: the program that the laptop, your scripts and any browser will ask for
   measurements from now on. (It is not Flight Deck; serving the Flight Deck page is one of the three
   things it does, so that a browser on this PC can show a measurement, which is half of the goal 1 demo
   in Part 8.) Its options: `--read-only` makes it the kind that drives no instrument. `--host 0.0.0.0`
   makes it listen on every network interface, so that other computers can reach it (the default would be
   this PC only). `--port 8700` is where the catalogue and the web page are served, and `--stream-port
   8765` is a second connection the web page uses to receive the measurement data it draws. `--ui` names
   the built web page, relative to the repository. `--root` names a scratch folder for the server's own
   bookkeeping, which it creates: a small database file, `cache.sqlite`, and a `payloads` subfolder, the
   same local cache every qdt program keeps (a measurement PC parks records there when `qdt-db` is
   unreachable). The read server barely uses it, but it must exist somewhere: on a local disk, outside the
   repository, and not inside the shared payload folder, where its own `payloads` subfolder would be
   confusing.

   The file contains the reader password, so restrict who can read it: right-click the file → Properties →
   Security, and remove every entry except *SYSTEM*, *Administrators* and your own account.

3. Run it by hand first. In PowerShell:

   ```powershell
   powershell -ExecutionPolicy Bypass -File C:\qdt\read-server.ps1
   ```

   (`-ExecutionPolicy Bypass` lets this one script run even if Windows is set to refuse unsigned scripts.)
   It prints a few lines ending with `Uvicorn running on http://0.0.0.0:8700`. Leave it running.

   **Check it** on this PC, in a browser:
   - `http://localhost:8700/server` shows a line of text beginning `{"read_only":true`. This is the server
     describing itself.
   - `http://localhost:8700/records` shows `[]`: an empty list, because nothing has been measured yet.
   - `http://localhost:8700/docs` shows the full list of questions the server answers. There is no way to
     start a measurement in it, by design.
   - `http://localhost:8700/` shows Flight Deck: a *History* pane on the left, a plot in the middle, and no
     *Run* button in the top strip.

   If `/server` answers but `/records` shows `Internal Server Error`, the server is running but cannot
   log in to the database: the password or account in the script is wrong. The PowerShell window shows
   the full error, and PostgreSQL's own log says it in one line: the newest file in
   `C:\Program Files\PostgreSQL\17\data\log\` ends with `password authentication failed for user
   "qdt_reader"`. Test the password on its own with `psql -U qdt_reader -h 127.0.0.1 -d qdt -c "SELECT 1;"`
   (Part 2's check), fix the script, and restart the server.

   Press Ctrl-C in the PowerShell window to stop it before the next step. Only one server can own the two
   ports: starting a second while the first is running fails with `only one usage of each socket address`
   (Appendix B says how to find the first).

4. Open the firewall for the two ports, as in Part 3, in PowerShell **as administrator**:

   ```powershell
   New-NetFirewallRule -DisplayName "qdt-db read server" -Direction Inbound -Protocol TCP -LocalPort 8700,8765 -RemoteAddress <lab-subnet> -Action Allow
   ```

   (**Over Tailscale:** `-RemoteAddress 100.64.0.0/10 -InterfaceAlias Tailscale`, as in Part 3, step 6.)

5. Make Windows start the server at boot, whether or not anyone logs in. Press the Windows key, type
   `task scheduler`, open it, and click *Create Task…* (not *Create Basic Task*). Then:
   - *General* tab: name it `qdt read server`; choose *Run whether user is logged on or not*; tick *Run
     with highest privileges*. The task runs as your account; Windows will ask for your password when you
     save, and stores it so the task can run with nobody logged in.
   - *Triggers* tab: *New…*, begin the task *At startup*, OK.
   - *Actions* tab: *New…*, action *Start a program*, program `powershell.exe`, arguments
     `-ExecutionPolicy Bypass -File C:\qdt\read-server.ps1`, OK.
   - *Conditions* tab: untick *Start the task only if the computer is on AC power* if it is a laptop.
   - *Settings* tab: tick *If the task fails, restart every* 1 minute, up to 3 times; set *Stop the task if
     it runs longer than* to *disabled* (clear the tick), because this task is meant to run forever.
   Click OK and enter your password.

**What changed.** The PC now has a scheduled task that starts the read server at every boot, and a firewall
rule that lets other computers reach it.

**Check it.** Restart the PC and do not log in. From the laptop, open a browser at
`http://qdt-db:8700/server`: it shows the `{"read_only":true` line. If it does not, log in to `qdt-db`,
open Task Scheduler, select the task, and read the *History* tab (if it says history is disabled, enable
it from the right-hand *Actions* panel and restart the task with *Run*). The most common cause is a typo
in the script path or a password that was not accepted.

Flight Deck itself must be opened with a longer address from another computer, because the page needs
to be told where its server is (issue #122 is about making this unnecessary):

```
http://qdt-db:8700/?api=http://qdt-db:8700&ws=ws://qdt-db:8765
```

Bookmark that on each desk. From `qdt-db` itself the short `http://localhost:8700/` is enough.

## Part 7 — The measurement PC

**What this does.** The program that drives the instruments and records measurements does not change. Two
permanent settings tell it where the database and the data folder are; from then on it copies each new
record to `qdt-db` as soon as the measurement ends.

1. On the laptop, as the user who will run the server, set the two variables permanently. The first is
   the database address, as `qdt_writer`; the second is the share, written the way that laptop's
   operating system names it.

   *Windows laptop*, in PowerShell. `setx` writes the values into your Windows account's settings; unlike
   `$env:`, they survive closing the window, but they become visible only in windows opened afterwards.

   ```powershell
   setx QDT_REGISTRY_DSN "postgresql+psycopg://qdt_writer:<writer password>@qdt-db:5432/qdt"
   setx QDT_PAYLOAD_STORE "\\qdt-db\qdt-payloads"
   ```

   Each prints `SUCCESS: Specified value was saved.` Close the window.

   *Mac laptop*, in Terminal. Permanent variables live in your shell's start-up file, which every new
   Terminal window reads. Open it with `nano ~/.zshrc` (the file is created if it does not exist), add
   these two lines at the end, save with Ctrl-O and Enter, and leave with Ctrl-X:

   ```
   export QDT_REGISTRY_DSN="postgresql+psycopg://qdt_writer:<writer password>@qdt-db:5432/qdt"
   export QDT_PAYLOAD_STORE="$HOME/qdt-payloads"
   ```

   The second is the mount point from Part 5, step 5; `$HOME` is filled in with your home folder when a
   window opens. Close the window. (A program started from the Dock or Finder rather than from Terminal does
   not read this file; start the stand server from Terminal.)

**What changed.** Any program you start from now on, from a new window, sees the two settings. The
project's stand server reads them when it starts: with them present it connects to the database as
`qdt_writer` and copies each record's data file to the share.

**Check it** in a new window, before running any measurement. First that the settings are there:
`echo $env:QDT_PAYLOAD_STORE` on Windows or `echo $QDT_PAYLOAD_STORE` on a Mac prints the share path.
Then that the database answers:

```
cd C:\qdt\repo        # Mac: cd ~/qdt/repo
uv run python -m qdt_registry find --remote
```

This asks the database on `qdt-db`, as the writer, for the list of records and prints `0 record(s)`. That
one line proves the address, the password, the firewall and the `pg_hba.conf` rule are all right. If it
prints a long error ending in `password authentication failed`, the password or account name in the
variable is wrong; if it ends in `no pg_hba.conf entry`, the laptop's address is outside the range from
Part 3; if it hangs for a long time and ends in `timeout expired`, the firewall or the name `qdt-db` is
the problem (issue #119 explains why the wait is long).

2. Start the stand server and Flight Deck as you always have, for example `uv run python -m qdt_server`
   and `corepack pnpm dev` in `apps\flightdeck`, and run one sweep. In the server's output, a successful
   copy prints nothing. If `qdt-db` cannot be reached you see one line, `registry sync failed; records stay
   in the local cache: …`, and the measurement is still complete and kept on the laptop; it is copied the
   next time a sync succeeds, together with anything else that is waiting. To copy by hand at any time,
   run `uv run python -m qdt_registry sync`.

## Part 8 — The demonstration

This is the smoke test the setup exists for: a measurement taken on the laptop, read on the desktop in
two different ways, with the laptop then switched off. Do it once now and again after any change to the
machines; the project's step file calls these checks R-1 to R-3.

1. **Measure on the laptop.** With the stand server and Flight Deck running on the laptop, set up a sweep
   and press *Run*. Wait for the strip to show `completed → record`.

2. **See it in Flight Deck on the desktop.** On `qdt-db`, open `http://localhost:8700/`. In the *History*
   pane press the refresh button; the sweep appears with its time, name and device. Press *open*: the
   measurement is drawn in the plot pane. Notice that the top strip has no *Run* button and the pane
   picker offers no sweep or levels widget: this server cannot operate anything.

3. **See it from a script.** On `qdt-db` (or any computer with the repository), the short way is the
   command-line tool, this time as the reader. The addresses below name the database PC as `qdt-db`.
   Whether that works depends on whether the computer you run this on knows that name: the laptop does,
   because you gave it the name in Part 3 (hosts file or Tailscale); the database PC itself usually does
   not, unless you added the name there as well. `ping qdt-db` tells you in one line. Where the name is not
   known, write the address instead: `127.0.0.1` on the database PC itself, or its network address from
   Part 3, step 1 on any other machine. Also, `uv run` must be started inside the repository folder (`cd`
   there first), or it cannot find the project's packages. Set the address for this window only, then ask:

   ```powershell
   $env:QDT_REGISTRY_DSN = "postgresql+psycopg://qdt_reader:<reader password>@qdt-db:5432/qdt"   # PowerShell
   uv run python -m qdt_registry find --remote
   ```

   (On a Mac the first line is `export QDT_REGISTRY_DSN="postgresql+psycopg://qdt_reader:<reader password>@qdt-db:5432/qdt"`.)

   It prints one line per record and `1 record(s)`. The longer way, which also fetches the measured data,
   is a few lines of Python. Save this as `read_one.py` inside the repository folder and run it there with
   `uv run python read_one.py`. The two addresses at the top follow the same rule as above: `qdt-db` where
   this computer knows the name, the address where it does not:

   ```python
   import hashlib, urllib.request
   from qdt_registry import Registry
   from qdt_schemas.payload_hdf5 import read_payload

   READER = "postgresql+psycopg://qdt_reader:<reader password>@qdt-db:5432/qdt"
   READ_SERVER = "http://qdt-db:8700"

   # 1. The catalogue, through the project's own client, as the read-only account.
   registry = Registry("my-cache", remote_dsn=READER)        # "my-cache" is a folder it makes for itself
   for r in registry.find(remote=True):
       print(r.started_at, r.definition_name, r.record_id)
   record = registry.find(remote=True)[-1]                     # the newest

   # 2. The measured data, as a file, from the read server, with its checksum verified.
   with urllib.request.urlopen(f"{READ_SERVER}/records/{record.record_id}/payload") as reply:
       data = reply.read()
       assert hashlib.sha256(data).hexdigest() == reply.headers["X-Content-SHA256"] == record.payload.sha256
   open("measurement.h5", "wb").write(data)

   # 3. The arrays themselves.
   payload = read_payload("measurement.h5")
   for name, array in payload.arrays.items():
       print(name, array.shape)
   ```

   The checksum line matters: it proves the bytes you received are the bytes the measurement PC wrote.
   `docs\tutorials\test_04_remote_read.py` in the repository is the same pattern, run automatically as
   a test.

4. **With the laptop off.** Shut the stand server down (or the whole laptop). Repeat steps 2 and 3: they
   must still work, because everything they need is on `qdt-db`. This is the point of having a separate
   database PC.

5. **After a reboot.** Restart `qdt-db` and leave it alone, without logging in. Repeat steps 2 (from the
   laptop, with the long address from Part 6) and 3. If they pass, the services really do start on their
   own.

## Part 9 — Backups, and proving they restore

**What this does.** Every night the database is written out to a single file, and the data folder is
mirrored to a second place. A backup you have never restored is a hope rather than a backup, so you
restore one into a scratch database once, now, and again on a date you put in the calendar.

1. Let the backup program log in without a password prompt. PostgreSQL's tools read passwords from a
   file named `pgpass.conf` in a folder named `postgresql` inside your account's *Roaming* folder, so
   the full path is:

   ```
   C:\Users\<you>\AppData\Roaming\postgresql\pgpass.conf
   ```

   Neither the `postgresql` folder nor the file exists yet. In PowerShell, logged in as the account the
   scheduled tasks run as (yours), these two lines create the folder and open the file in Notepad:

   ```powershell
   New-Item -ItemType Directory -Force "$env:APPDATA\postgresql" | Out-Null
   notepad "$env:APPDATA\postgresql\pgpass.conf"
   ```

   (`$env:APPDATA` is Windows's name for the *Roaming* folder, which is why PostgreSQL's own
   documentation writes the path as `%APPDATA%\postgresql\pgpass.conf`. It is a placeholder, not a
   folder you will find.) Answer *Yes* when Notepad asks whether to create the file, put one line in it
   and save:

   ```
   127.0.0.1:5432:qdt:qdt_admin:<admin password>
   ```

   The format is host, port, database, account, password. Restrict the file's permissions to your own
   account as you did for the script in Part 6. **Check it:** `Get-ChildItem $env:APPDATA\postgresql`
   lists exactly `pgpass.conf` (not `pgpass.conf.txt`, which Notepad adds if you type the name into its
   Save dialog yourself), and `psql -U qdt_admin -h 127.0.0.1 qdt -c "select 1"` connects without asking
   for a password.

2. Create the backup folder and script. Make `C:\qdt\backup`, and save this as `C:\qdt\backup.ps1`,
   replacing `<backup host>` with the machine or NAS that holds the copy of the data files (it must not be
   `qdt-db` itself, and it must have a share you can write to):

   ```powershell
   $stamp = Get-Date -Format yyyyMMdd
   pg_dump -U qdt_admin -h 127.0.0.1 -Fc -f "C:\qdt\backup\qdt-$stamp.dump" qdt
   Get-ChildItem C:\qdt\backup\qdt-*.dump | Sort-Object Name -Descending | Select-Object -Skip 30 | Remove-Item
   robocopy C:\qdt\payloads \\<backup host>\qdt-payloads /MIR /R:2 /W:5 /LOG:C:\qdt\backup\payloads.log
   ```

   The first line makes a date such as `20261022`. `pg_dump` writes the whole database into one compressed
   file (`-Fc`) named with the date. The third line keeps the newest thirty dumps and deletes older ones.
   `robocopy … /MIR` mirrors the data folder to the backup share, copying only what changed, and writes a
   log; `/R:2 /W:5` means retry a failing file twice, five seconds apart, rather than for ever.

3. Schedule it as in Part 6, step 5, named `qdt backup`, triggered *Daily* at 02:00, with the action
   `powershell.exe -ExecutionPolicy Bypass -File C:\qdt\backup.ps1`. Run it once by hand from Task
   Scheduler (*Run* in the right-hand panel). **Check it:** `C:\qdt\backup` contains a file
   `qdt-<today>.dump` larger than zero bytes, and `payloads.log` ends with a summary whose *FAILED*
   column is 0.

4. **The restore drill.** This creates a scratch database from last night's file, counts the records in
   it, and throws it away. Run it in PowerShell; it asks for the superuser password a few times.

   ```powershell
   psql -U postgres -d postgres -c "CREATE DATABASE qdt_drill;"
   pg_restore -U postgres -d qdt_drill C:\qdt\backup\qdt-<date>.dump
   psql -U postgres -d qdt_drill -c "SELECT count(*) FROM records;"
   psql -U postgres -d postgres -c "DROP DATABASE qdt_drill;"
   ```

   The count must equal what `http://localhost:8700/records` lists. `pg_restore` may print warnings about
   roles it could not find; they are harmless here. Write the date of the drill into the step's bench
   report, `bench\reports\<date>-step6c.md`, and put the next one in the calendar.

## Part 10 — What only a person at the machine can confirm

The sessions that wrote this document cannot see your PC. After each run through this file, confirm:

- [ ] In *Services*, `postgresql-x64-17` (or `-18`) is *Running* and *Automatic*, and still is after a reboot.
- [ ] From the laptop, connecting as `qdt_writer` and as `qdt_reader` works; connecting as `qdt_admin` or
      `postgres` from the laptop is refused (there is no `pg_hba.conf` line for them).
- [ ] From the laptop, the share (`\\qdt-db\qdt-payloads` on Windows, `~/qdt-payloads` on a Mac)
      can be written to after the laptop reboots, without a password prompt; opening it as a guest without
      a password is refused. On a Mac, with the share unmounted, writing into `~/qdt-payloads` is refused.
- [ ] From the laptop, `http://qdt-db:8700/server` answers after `qdt-db` reboots with nobody logged in.
- [ ] Last night's `.dump` file exists and is not empty; the robocopy log shows no failed copies.
- [ ] The restore drill has been done once, and its date is in the bench report.
- [ ] Windows Update's automatic-restart behaviour is agreed with whoever administers the machine, so the
      PC does not restart in the middle of a measurement (plan §9).

## Appendix A — Running the project's Postgres tests without Docker (issue #112)

The repository's test suite has a handful of tests that need a real PostgreSQL. Developers usually
provide one with Docker; the PostgreSQL you installed above serves just as well. Create a scratch
database for the tests, owned by an account named `qdt` with password `qdt` (the names the tests
expect), and give the three roles the same permissions on it:

```powershell
psql -U postgres -d postgres -c "CREATE ROLE qdt LOGIN PASSWORD 'qdt' CREATEDB;"
psql -U postgres -d postgres -c "CREATE DATABASE qdt_test OWNER qdt;"
psql -U postgres -d postgres -v db=qdt_test -v admin_pw='x' -v writer_pw='x' -v reader_pw='x' -f deploy\qdt-db\roles.sql
psql -U qdt -d qdt_test -c "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO qdt_reader;"
```

(If the three roles already exist from Part 2, the `CREATE ROLE` lines in the file fail and the rest
still runs; that is fine. The last line is needed because the tests create their tables as `qdt`, not as
`qdt_admin`.) Then, in the window where you run the tests:

```powershell
$env:QDT_TEST_PG_DSN = "postgresql+psycopg://qdt:qdt@127.0.0.1:5432/qdt_test"
$env:QDT_TEST_PG_READER_DSN = "postgresql+psycopg://qdt_reader:<reader password>@127.0.0.1:5432/qdt_test"
uv run pytest packages/qdt-registry docs/tutorials
```

The tests that were reported as *skipped* before now run. They drop and recreate the tables in
`qdt_test` every time, so never point these two variables at the real `qdt` database. Use `127.0.0.1`
rather than `localhost`: on Windows, `localhost` is tried over IPv6 first and every connection waits a
few seconds before falling back.

## Appendix B — Messages you may see, and what they mean

| Where | Message | Meaning and fix |
|---|---|---|
| `psql`, Python | `password authentication failed for user "…"` | The password in the command or in `QDT_REGISTRY_DSN` is wrong for that account. Check the password manager; check the account name. |
| `psql`, Python | `no pg_hba.conf entry for host "…", user "…", database "qdt"` | The connecting computer's address is not covered by the lines you added in Part 3, or the account has no line. Check the range; restart the service after editing. |
| `psql`, Python | `connection refused` | The server is not listening on that address: `listen_addresses` not changed, service not restarted, or the wrong host name. |
| `psql`, Python | `timeout expired` / a long wait then an error | The firewall is blocking the port, or `qdt-db` does not resolve to the right address. Use `Test-NetConnection qdt-db -Port 5432` from the laptop. |
| Python | `permission denied for table records` | A write was attempted as `qdt_reader`. Scripts read; only the measurement PC writes, as `qdt_writer`. |
| Python | `registry at … has ddl_version 2; this client expects 3` | The database's tables are from an older version of the software than the program connecting to it. Update the repository on `qdt-db` and run `python -m qdt_registry init` again as the admin; update the other machines too. |
| stand server log | `registry sync failed; records stay in the local cache: …` | `qdt-db` or the share was unreachable when a measurement finished. Nothing is lost; the record is copied with the next successful sync. The text after the colon says which of the two it was. |
| File Explorer | `Windows cannot access \\qdt-db\qdt-payloads` | The network profile is *Public* (over Tailscale: no port-445 rule for the Tailscale adapter), the share permission is missing, or the credentials were not stored. Part 5, steps 3–5. |
| Finder (Mac) | `There was a problem connecting to the server "qdt-db"` | Same causes as the row above; also check the name resolves (`ping qdt-db`) and that you chose *Registered User*, not *Guest*. |
| stand server log (Mac) | `registry sync failed … Permission denied: '/Users/…/qdt-payloads/…'` | The share is not mounted on the Mac (the read-only mount point refused the write, as intended). `bash deploy/qdt-db/mac-payload-mount.sh check` shows what the last attempt logged; running it without `check` mounts again. The waiting record is copied on the next sync. |
| Python | `Can't load plugin: sqlalchemy.dialects:postgreswl.psycopg` (or any spelling other than `postgresql.psycopg`) | A typo in the first word of `QDT_REGISTRY_DSN`. It must begin exactly `postgresql+psycopg://`. |
| read server window | `error while attempting to bind on address ('0.0.0.0', 8765) … only one usage of each socket address` | A read server is already running on this PC (an earlier window, or the scheduled task from Part 6, step 5). Only one can own the ports. To find it: `Get-NetTCPConnection -LocalPort 8700 \| Select-Object OwningProcess`, then `Stop-Process -Id <that number>`, or press Ctrl-C in its window. If the scheduled task started it, it is doing its job; leave it. |
| browser, read server | `http://localhost:8700/server` answers but `/records` shows `Internal Server Error` | The server cannot log in to the database: the reader password or account in `read-server.ps1` is wrong. PostgreSQL's log (newest file in `C:\Program Files\PostgreSQL\17\data\log\`) says `password authentication failed for user "qdt_reader"`. Part 6, step 3. |
| read server window, on *open* in History | `FileNotFoundError: … Unable to synchronously open file … 'C:\qdt\payloads\2026\…h5'` | The record is in the database but the server looks for its data file in the wrong folder: `QDT_PAYLOAD_STORE` in `read-server.ps1` must be the shared folder's local path on this PC (`Get-SmbShare -Name qdt-payloads` prints it), not the example path. Fix the script, Ctrl-C the server, start it again. |
| Python | `failed to resolve host 'qdt-db': [Errno 11001] getaddrinfo failed` (or `URLError … getaddrinfo failed`) | This machine does not know the name `qdt-db`. On the database PC itself that is normal: use `127.0.0.1` in the address (Part 8, step 3). On a laptop, the name is missing: Part 3, step 5 (hosts file), or Tailscale is not connected. |
| PowerShell | `The argument '…\read-server.ps1' to the -File parameter does not exist` | No file has exactly that name. `Get-ChildItem` on its folder shows the real name; usually it is `read-server.ps1.txt` (Notepad added `.txt`): `Rename-Item …\read-server.ps1.txt read-server.ps1`. Part 6, step 2 says how to create it with the right name. |
| browser | Flight Deck shows `connecting…` and an empty History from the laptop | The page was opened with the short address. Use the long one from Part 6 with `?api=` and `?ws=`. |
