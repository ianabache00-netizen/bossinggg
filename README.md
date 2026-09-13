ZENTRIX GENERATOR BOT — Railway Deployment

UI Features (matches your sample picture)
- 2-column stock buttons: `GARENA (173.8K)` style with live line counts
- `Next Page` / `Prev Page` pagination (8 stocks per page)
- `Main Menu` button at the bottom of every menu
- Full inline-button interface — no typing needed

Deploy on Railway

1. Push to GitHub
Upload this folder as a GitHub repo (files must be in the root — not inside another folder).

2. Create Railway project
- railway.app → New Project → Deploy from GitHub repo
- Select your repo → Railway auto-detects Python and reads `railway.toml`

3. Set Variables
Railway project → Variables → add:

Key	Value	
`BOT_TOKEN`	token from @BotFather	
`ADMIN_IDS`	your Telegram user ID (comma-separated for multiple)	

4. Generate domain (for health check)
Settings → Networking → Generate Domain (keeps the service awake/healthy).

Done — bot runs 24/7.

Commands

User

Command	Description	
/start	Main menu	
/redeem KEY	Redeem key (required before generating)	
/generate	Pick stock from grid → receive TXT	
/stock	Stock list with line counts	
/me	Tier, key, total generations	

Admin

Command	Description	
/genkey	Reply `Premium 5` or `Platinum 3`	
/addstock	Send .txt or .zip file → added to stock	
/revoke USER_ID	Remove user access	
/check USER_ID	View user generations	

Stock Management — 3 ways
1. ZArchiver (local): extract `.txt` files into `stock/` folder
2. Telegram: send the `.txt`/`.zip` file to the bot → auto-added (admin only)
3. GitHub: push `.txt` files into `stock/` → Railway redeploys

⚠️ Railway's filesystem is ephemeral — stock added via Telegram/ZArchiver-style disappears on redeploy.
For permanent stock, commit files to GitHub, or re-upload after redeploys.

Key Tiers

Tier	Expiration	Lines per generate	
Premium	Never	3,000	
Platinum	Never	2,500	

Format: `Premium-123-456-789` · 1 key = 1 user · lines never duplicated (offset tracked per file)
