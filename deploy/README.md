# Deploying Ask Onboarding

This puts Ask Onboarding on a public HTTPS address, behind a password. The server runs the same `docker compose` stack as your laptop, plus Caddy in front ([docker-compose.prod.yml](docker-compose.prod.yml)):

- **Only Caddy is reachable from the internet** (ports 80 and 443). The database, API and model can't be reached from outside.
- **Caddy gets a free HTTPS certificate** and asks for a username and password, because the app has no login.

The app runs a local model (qwen2.5:3b) that needs about 4 GB of RAM, so the server needs **at least 8 GB**. That rules out most free tiers, which give 1 GB or less. Two options work:

| | Google Cloud free trial (recommended) | Oracle Cloud Always Free |
| --- | --- | --- |
| Cost | $300 credit for 90 days, with no charge afterwards unless you upgrade | Free forever |
| Server | e2-standard-4: 4 CPUs, 16 GB | Ampere A1: 4 ARM CPUs, 24 GB |
| Catch | Ends after 90 days | Free ARM servers are often **out of capacity**, especially in small regions |

Both need a card to verify you. After you connect to the server, the steps are the same.

## Option A: Google Cloud (free trial)

### 1. Start the trial

Go to https://cloud.google.com/free, click **Get started for free**, and sign in with a Google account. Enter your country and card, and you get $300 of credit for 90 days.

### 2. Create the server

In the console, open **☰ → Compute Engine → VM instances**. If asked, click **Enable** for the Compute Engine API and wait a minute. Then click **Create instance**:

| Setting | Value |
| --- | --- |
| Name | `ask-onboarding` |
| Region | One near you, for example `me-central1 (Doha)` or `europe-west2 (London)`. Any zone. |
| Machine configuration | **E2 → e2-standard-4** (4 vCPUs, 16 GB) |
| OS and storage → Change | **Ubuntu → Ubuntu 24.04 LTS (x86/64)**, not "Minimal". **Balanced persistent disk, 50 GB**. The default 10 GB is too small: the images and the model need about 20 GB. |
| Networking → Firewall | Tick **Allow HTTP traffic** and **Allow HTTPS traffic** |

Click **Create**. The estimate on the right of the page should show about $100–130 a month, which comes out of the credit.

**Optional, but recommended:** keep the address from changing. A Google server gets a new public IP if it's stopped and started again, and the site address is built from the IP. To keep it, go to **☰ → VPC network → IP addresses**, find the server's external address, then click **⋮ → Promote to static IP address**.

### 3. Connect

On the **VM instances** page, click **SSH** on the server's row. A terminal opens in your browser; click **Authorize** if asked. Then continue with [Install and start](#install-and-start).

## Option B: Oracle Cloud (Always Free)

1. **Account.** Sign up at https://signup.cloud.oracle.com. Your home region can't be changed later, and free servers only run there.
2. **Server.** Open **☰ → Compute → Instances → Create instance**:
   - **Image:** Canonical Ubuntu 24.04, not "Minimal".
   - **Shape:** **Ampere → VM.Standard.A1.Flex**, with 4 OCPUs and 24 GB, or 2 OCPUs and 12 GB, which is easier to get.
   - **Public IP:** on.
   - **SSH key:** choose **Generate a key pair for me** and save the private key.
   - **"Out of capacity":** try another availability domain or try later. Upgrading the account to Pay As You Go helps the most; Always Free resources stay free.
3. **Firewall.** On the instance page, click the subnet, then **Security → Default Security List → Add Ingress Rules**: source `0.0.0.0/0`, TCP, destination ports `80,443`.
4. **Connect** from PowerShell. The first command makes the key readable only by you, because SSH refuses keys that other users can read:
   ```powershell
   icacls $HOME\.ssh\oracle-ask.key /inheritance:r /grant:r "$($env:USERNAME):R"
   ssh -i $HOME\.ssh\oracle-ask.key ubuntu@<public-ip>
   ```

Oracle can stop Always Free servers that stay almost idle for 7 days. Pay As You Go accounts are exempt.

## Install and start

On the server:

```bash
sudo apt-get update && sudo apt-get install -y git   # minimal images don't include git
git clone https://github.com/yunuskalam-ai/ask-onboarding.git
cd ask-onboarding
bash deploy/setup.sh
```

The script ([setup.sh](setup.sh)) first installs anything else a minimal image leaves out (`curl`, `openssl`, and `iptables`, which Docker needs). Then it does four things:
1. **Opens ports 80 and 443 in the server's own firewall.** Oracle needs this; on Google it changes nothing.
2. **Installs Docker.**
3. **Asks for a username and password for the site** and writes `.env`. It stores only a hash of the password, and a random database password.
4. **Runs `docker compose up -d --build`.**

The site address is your server's IP with dashes, through [sslip.io](https://sslip.io), for example `https://34-18-1-2.sslip.io`. This gives Caddy a host name it can get a certificate for, without you buying a domain.

The first start builds the images and downloads the model, about 10–15 minutes on a cloud network. Then open the address and log in.

## Day-to-day

| Task | Command (in `~/ask-onboarding`) |
| --- | --- |
| Watch the logs | `sudo docker compose logs -f` |
| Check that everything runs | `sudo docker compose ps` |
| Deploy new commits | `git pull && sudo docker compose up -d --build` |
| Stop / start | `sudo docker compose stop` / `sudo docker compose up -d` |
| Change the password | Delete `.env`, run `bash deploy/setup.sh` again, then `sudo docker compose up -d --force-recreate caddy` |

Documents, tickets and the model are kept in Docker volumes, so they survive restarts. Every service restarts automatically, including after a reboot.

## Troubleshooting

- **`sudo: I'm sorry …, I'm afraid I can't do that`** (Google Cloud). `sudo` stops working a few minutes after you open SSH-in-browser: Google's agent grants your user admin rights when the browser connects and later takes them away. Close the SSH window, open it again, and **straight away** make the rights permanent:
  ```bash
  echo "$USER ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/90-$USER
  ```
  Then run `bash deploy/setup.sh` again. It skips whatever is already done.

- **The page doesn't load.** Check the cloud firewall: on Google, the two checkboxes; on Oracle, the ingress rule. Then run `sudo docker compose ps`. Every service should be running or healthy, and `ollama-pull` should show exited (0).
- **There's a certificate error.** Caddy gets the certificate on the first visit and needs port 80 open for it. Run `sudo docker compose logs caddy`.
- **"Could not reach the local model".** The model is still downloading or loading. Run `sudo docker compose logs ollama-pull ollama`.
- **The address changed after a restart** (Google). Promote the IP to static (see step 2). Then update `SITE_ADDRESS` in `.env` and run `sudo docker compose up -d --force-recreate caddy`.

## Good to know

- **Speed:** the model runs on CPU, so the first words of an answer take about 10–20 s.
- **The password protects the whole site,** including uploads and tickets. Share it only with the people reviewing the project.
