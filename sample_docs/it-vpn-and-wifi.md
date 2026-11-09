# IT: VPN and Wi-Fi

## When you need the VPN

Use the **YK Labs VPN** to reach internal systems. You need it for:

- Staging (staging.routewise.example) and other internal tools
- The admin panels of production systems (on-call engineers only)
- **All work from outside the UK**, at all times

You do **not** need the VPN for Google Workspace, Slack, Notion, Jira or other cloud apps you sign in to through Okta.

## Setting up the VPN

1. Open the **Self Service** app and install **YK Labs VPN**.
2. Open YK Labs VPN and click **Sign in with Okta**.
3. Approve the push notification in Okta Verify.
4. Choose the **London** gateway. Use **Manchester** only if London is down.

The VPN disconnects after **12 hours**. Sign in again to reconnect.

## VPN problems

| Problem | Fix |
| --- | --- |
| "Device not compliant" | Install pending macOS updates, then restart |
| Connected but staging won't load | Disconnect, wait 10 seconds and reconnect; then clear your browser's DNS cache |
| Very slow connection | Switch gateway, or check your home internet speed without the VPN |
| Still not working | Post in #it-help with a screenshot of the error |

## Office Wi-Fi

| Network | Who it is for | How to join |
| --- | --- | --- |
| YKLabs-Staff | Employees, company laptops | Sign in with your Okta username and password |
| YKLabs-Guest | Visitors and personal phones | Password shown on the reception screen |

- The **YKLabs-Guest** password changes every **Monday** morning.
- Do not connect company laptops to YKLabs-Guest.
- YKLabs-Guest has no access to internal systems, even with the VPN.

## Working from cafés and public Wi-Fi

Public Wi-Fi is fine for cloud apps. Turn on the VPN before opening internal tools. Never work on Restricted data in a public place where others can see your screen.
