# Oracle Cloud Always Free — Deployment Guide

Deploy the Credit Card Data Extractor on Oracle Cloud's **Always Free** ARM VM.
Total cost: **$0/month forever**.

## What You Get (Free)

| Resource | Spec |
|----------|------|
| VM | 4 ARM cores (Ampere A1), 24 GB RAM |
| Storage | 200 GB boot volume |
| Bandwidth | 10 TB outbound/month |
| Public IP | 1 static reserved IP |

## Step 1: Create Oracle Cloud Account

1. Go to https://cloud.oracle.com/
2. Click **Start for free**
3. Sign up with email + credit card (won't be charged)
4. Select a **Home Region** close to you (e.g., `me-dubai-1` for UAE, `eu-frankfurt-1` for EU)
5. Wait for account to be provisioned (can take a few minutes)

## Step 2: Create the ARM VM

### Via Console (cloud.oracle.com):

1. Go to **Compute → Instances → Create Instance**
2. Configure:
   - **Name**: `card-extractor`
   - **Image**: Ubuntu 24.04 (Canonical)
   - **Shape**: Click "Change Shape" →
     - Shape series: **Ampere** (ARM)
     - Shape: **VM.Standard.A1.Flex**
     - OCPUs: **4**
     - Memory: **24 GB**
   - **Networking**: Select default VCN or create new
     - Check **Assign a public IPv4 address**
   - **SSH Key**: Upload your public key or generate new
     - Save the private key if generated!
   - **Boot volume**: 50 GB is enough (default)
3. Click **Create**

### Via OCI CLI (alternative):

```bash
# Install OCI CLI
bash -c "$(curl -L https://raw.githubusercontent.com/oracle/oci-cli/master/scripts/install/install.sh)"
oci setup config

# Create VM (replace compartment-id and subnet-id)
oci compute instance launch \
  --availability-domain "xxxx:ME-DUBAI-1-AD-1" \
  --compartment-id "ocid1.compartment.oc1..xxxx" \
  --shape "VM.Standard.A1.Flex" \
  --shape-config '{"ocpus": 4, "memoryInGBs": 24}' \
  --image-id "ocid1.image.oc1..xxxx" \
  --subnet-id "ocid1.subnet.oc1..xxxx" \
  --assign-public-ip true \
  --ssh-authorized-keys-file ~/.ssh/id_rsa.pub \
  --display-name "card-extractor"
```

> **Note**: ARM capacity is limited in popular regions. If you get an "Out of
> capacity" error, try a different availability domain or region, or retry
> later. Many people report success within a few hours.

## Step 3: Open Firewall Ports

### In OCI Console:

1. Go to **Networking → Virtual Cloud Networks** → your VCN
2. Click **Security Lists** → Default Security List
3. Click **Add Ingress Rules**:
   - Source CIDR: `0.0.0.0/0`
   - Destination Port Range: `80`
   - Description: HTTP
4. Add another rule:
   - Source CIDR: `0.0.0.0/0`
   - Destination Port Range: `443`
   - Description: HTTPS

### On the VM (iptables — also required!):

OCI uses both security lists AND OS-level firewall. After SSH:

```bash
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save
```

## Step 4: SSH and Deploy

```bash
# SSH into VM (use your VM's public IP)
ssh -i ~/.ssh/your_key ubuntu@<VM_PUBLIC_IP>

# Run the setup script (copy it to VM first, or just run the commands below)
```

### One-Command Setup:

Upload the project zip to the VM:

```bash
# From your local machine:
scp -i ~/.ssh/your_key data-extraction-tool-full.zip ubuntu@<VM_PUBLIC_IP>:~
```

Then on the VM:

```bash
# Run the automated setup script
chmod +x ~/setup-oracle.sh
~/setup-oracle.sh
```

Or manually:

```bash
# 1. Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# 2. Unzip project
sudo apt install -y unzip
unzip data-extraction-tool-full.zip -d app
cd app

# 3. Configure
cp .env.example .env

# 4. Deploy
chmod +x deploy.sh
./deploy.sh
```

## Step 5: Access Your App

Open in browser: `http://<VM_PUBLIC_IP>`

## Step 6: Add a Domain + HTTPS (Optional)

1. Get a free domain from [freenom](https://freenom.com) or use your own
2. Point the domain's A record to your VM's public IP
3. Run SSL setup:

```bash
cd ~/app
./setup-ssl.sh yourdomain.com
```

## Monitoring

```bash
# Check all containers
docker compose ps

# Follow logs
docker compose logs -f
docker compose logs -f backend

# Check resource usage
docker stats

# Restart after issues
docker compose restart
```

## Troubleshooting

### "Out of capacity" when creating VM
ARM instances are popular. Try:
- Different availability domain (AD-1, AD-2, AD-3)
- Different region
- Retry every few hours (automated scripts exist for this)
- Start with a smaller shape (2 OCPU, 12 GB) and resize later

### Docker build fails on ARM
All our images are ARM-compatible. If an issue occurs:
```bash
docker compose build --no-cache
```

### Ollama is slow
The ARM A1 cores are efficient but not as fast as x86 for LLM inference.
Ollama with `phi` model should respond in 10-30 seconds per query.
This is normal for CPU-only inference on free tier.

### VM stops/gets reclaimed
Oracle may reclaim idle Always Free instances. To prevent this:
- Keep some activity (a cron job pinging your health endpoint works)
- Upgrade to Pay-As-You-Go (you still only pay for what exceeds free tier)

```bash
# Add keep-alive cron
(crontab -l 2>/dev/null; echo "*/5 * * * * curl -sf http://localhost/health > /dev/null") | crontab -
```
