# Deploying to Oracle Cloud (Always Free)

This guide puts Ask Onboarding on a public HTTPS address, behind a password, at no cost. The server runs the same `docker compose` stack as your laptop, plus Caddy in front ([docker-compose.prod.yml](docker-compose.prod.yml)).

**Why Oracle:** the app runs a local model (qwen2.5:3b) that needs about 4 GB of RAM. Oracle's Always Free tier includes an ARM server with 4 CPUs and 24 GB of RAM. Most other free tiers give 1 GB or less.

**Time:** about 15 minutes of clicking, then about 15 minutes of building.

## 1. Create the account

1. Sign up at https://signup.cloud.oracle.com.
2. Pick your **home region** carefully, because it can't be changed later. Choose one near you.
3. Oracle asks for a card to verify you are a real person. Always Free resources are never charged.

## 2. Create the server

In the Oracle Cloud console, open **☰ → Compute → Instances → Create instance**.

| Setting | Value |
| --- | --- |
| Name | `ask-onboarding` |
| Image | **Change image → Ubuntu → Canonical Ubuntu 24.04**. Pick the normal image, not "Minimal". |
| Shape | **Change shape → Ampere → VM.Standard.A1.Flex**, with **4 OCPUs** and **24 GB** of memory. It shows an "Always Free-eligible" label. |
| Networking | Keep the defaults: a new virtual cloud network with a public subnet. Make sure **Assign a public IPv4 address** is on. |
| SSH keys | **Generate a key pair for me → Save private key**. Keep the file safe, for example as `C:\Users\<you>\.ssh\oracle-ask.key`. |
| Boot volume | Optional: set the size to **100 GB**. Up to 200 GB in total is free; the default 47 GB also works. |

Click **Create**. When the instance shows **Running**, copy its **Public IP address**.

> **"Out of capacity"?** Free ARM servers are popular. Try another **Availability domain** on the same page, or try again a few hours later.

## 3. Open ports 80 and 443 in Oracle's firewall

On the instance page, click the **subnet** link, then **Security → Default Security List**. Click **Add Ingress Rules**:

| Field | Value |
| --- | --- |
| Source CIDR | `0.0.0.0/0` |
| IP Protocol | TCP |
| Destination Port Range | `80,443` |

The server has a second firewall of its own; the setup script opens that one.

## 4. Connect to the server

From PowerShell on Windows, first make the key readable only by you (SSH refuses keys other users can read), then connect:

```powershell
icacls $HOME\.ssh\oracle-ask.key /inheritance:r /grant:r "$($env:USERNAME):R"
ssh -i $HOME\.ssh\oracle-ask.key ubuntu@<public-ip>
```

Type `yes` when it asks whether to trust the server.

## 5. Install and start

On the server:

```bash
git clone https://github.com/yunuskalam-ai/ask-onboarding.git
cd ask-onboarding
bash deploy/oracle/setup.sh
```

The script ([setup.sh](setup.sh)) does four things:
1. Opens ports 80 and 443 in the server's firewall.
2. Installs Docker.
3. Asks you for a **username and password for the site** and writes `.env`, which stores only a hash of the password.
4. Runs `docker compose up -d --build`.

The address is your IP with dashes, through [sslip.io](https://sslip.io), for example `https://140-238-1-2.sslip.io`. This gives Caddy a host name it can get a free HTTPS certificate for, without you buying a domain.

The first start builds the images and downloads the model, about 10–15 minutes in total. Then open the address and log in with the username and password you chose.

## Day-to-day

| Task | Command (in `~/ask-onboarding`) |
| --- | --- |
| Watch the logs | `sudo docker compose logs -f` |
| Deploy new commits | `git pull && sudo docker compose up -d --build` |
| Stop / start | `sudo docker compose stop` / `sudo docker compose up -d` |
| Change the password | Delete `.env`, run `bash deploy/oracle/setup.sh` again, then `sudo docker compose up -d --force-recreate caddy` |

Documents, tickets and the model are kept in Docker volumes, so they survive restarts and reboots. Every service restarts automatically.

## Troubleshooting

- **The page doesn't load at all.** Check that the ingress rule in step 3 exists and the instance is running. Then run `sudo docker compose ps`; every service should be `running` or `healthy`, and `ollama-pull` should be `exited (0)`.
- **There's a certificate error.** Caddy gets the certificate on the first visit and needs port 80 open for it. Run `sudo docker compose logs caddy`.
- **"Could not reach the local model".** The model is still downloading or loading. Run `sudo docker compose logs ollama-pull`.

## Good to know

- **Oracle can reclaim idle free servers.** An Always Free instance that stays almost idle for 7 days may be stopped. Upgrading the account to Pay As You Go prevents this, and Always Free resources stay free.
- **Speed is similar to a laptop.** The model runs on CPU, so the first words of an answer take about 10–20 s.
- **The password protects the whole site,** including uploads and tickets. Share it only with the people reviewing the project.
