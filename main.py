import discord
from discord.ext import commands
from discord import app_commands
import os, random, time, asyncio, aiohttp, gc
from motor.motor_asyncio import AsyncIOMotorClient
from PIL import Image
from io import BytesIO

# ======================
# 💎 CONFIG & TOKENS
# ======================
TOKEN = os.getenv("TOKEN")
MONGO = os.getenv("MONGO")
CURRENCY = "Relics"
LOG_CHANNEL_ID = 1496151311836512378

# Cooldowns (in seconds)
DROP_CD = 300
CLAIM_CD = 120
DAILY_CD = 79200

# Staff IDs
STAFF_IDS = [1106193228971122689, 702667135775801376, 701969588157415506, 701968449462599752, 871159389799743488]

# Rarity Mapping
RARITIES = ["whisper", "cherub", "siren", "enthrall", "devotion", "fallen", "eclipse", "velour", "sanctum"]
RARITY_ICONS = {
    "whisper": "https://cdn.discordapp.com/attachments/1487054242244984957/1487872174323667014/Untitled13_20260329154525.png?ex=69e9b3b1&is=69e86231&hm=839457854104f56ba4f2ce938c3b5259dcf742cfbc9ae7dc95fe506212712440&", "cherub": "https://cdn.discordapp.com/attachments/1487054242244984957/1487872287729258739/Untitled13_20260329155942.png?ex=69e9b3cc&is=69e8624c&hm=2629964df5ec4f4d1da8bd3bf41538f1ba8c21d88124328ea8e5bbd169655464&", "siren": "https://cdn.discordapp.com/attachments/1487054242244984957/1487872389701308426/Untitled13_20260329183750.png?ex=69e9b3e5&is=69e86265&hm=c8a826a1c09fc2e3396a77ddfb2b6eab94a6a547996a1351176f08244ccd972b&", "enthrall": "https://cdn.discordapp.com/attachments/1487054242244984957/1487880470644523149/Untitled13_20260329235353.png?ex=69e9bb6b&is=69e869eb&hm=f2114ed570fc88bc24d9426a8ae02a5d02d73ccd77cde67a1dc92d1f54eb78ef&", 
    "devotion": "https://cdn.discordapp.com/attachments/1487054242244984957/1487880569500209243/Untitled13_20260329185342.png?ex=69e9bb83&is=69e86a03&hm=9c01237c2d15797f468ba1ea014c8bece064a13f8a00b3c3e364e6f0da828c03&", "fallen": "https://cdn.discordapp.com/attachments/1487054242244984957/1487881032261828710/Untitled13_20260329194919.png?ex=69e9bbf1&is=69e86a71&hm=196244aff41824e2ce458ec918dc28d603a481c28f58bb3472ab01fe6a6a607b&", "eclipse": "https://cdn.discordapp.com/attachments/1487054242244984957/1487881115988394037/Untitled13_20260329201615.png?ex=69e9bc05&is=69e86a85&hm=0f96fd40713360ef4272407f5cb04f1f3732b53bd84240e2022f55f4ba801061&", "velour": "https://cdn.discordapp.com/attachments/1487054242244984957/1487881187421720797/Untitled13_20260329001614.png?ex=69e9bc16&is=69e86a96&hm=694372b82e88553526e74917db843af196182f29dadca6dd73c7cd7df18b4beb&", "sanctum": "https://cdn.discordapp.com/attachments/1487054242244984957/1487881249191235604/Untitled13_20260329231514.png?ex=69e9bc25&is=69e86aa5&hm=fd4ae895148d137f37589fd20b0cd367a8ed7f87ca0271caa040df731a9c37ac&"
}
RARITY_CHOICES = [app_commands.Choice(name=r.title(), value=r) for r in RARITIES]

# ======================
# 🔌 DATABASE SETUP
# ======================
mongo = AsyncIOMotorClient(MONGO)
db = mongo["kpop"]
cards = db["cards"]
users = db["users"]

bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
tree = bot.tree

# Global RAM cache for card backs (prevents redownloading)
back_cache = {}

# ======================
# 🛠️ UTILITIES
# ======================
def is_staff(uid): return uid in STAFF_IDS

async def log_action(message):
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel: await channel.send(message)

async def get_card():
    """Selects a random card based on rarity weights."""
    for _ in range(5):
        r = random.random()
        if r < 0.1: chances = {"whisper":30,"cherub":25,"siren":17,"enthrall":12,"devotion":8,"eclipse":5,"velour":3}
        elif r < 0.3: chances = {"whisper":30,"cherub":25,"siren":20,"enthrall":12,"devotion":8,"eclipse":5}
        else: chances = {"whisper":35,"cherub":30,"siren":20,"enthrall":10,"devotion":5}
        
        rarity = random.choices(list(chances), list(chances.values()))[0]
        res = await cards.aggregate([{"$match":{"rarity":rarity,"droppable":True}}, {"$sample":{"size":1}}]).to_list(1)
        if res: return res[0]
    return None

async def get_back(card):
    if card.get("rarity_back"): return card["rarity_back"]
    return card.get("image_url")

# ======================
# 🖼️ MEMORY-SAFE MERGE
# ======================
async def merge_images(urls):
    async with aiohttp.ClientSession() as session:
        imgs = []
        try:
            for url in urls:
                if url in back_cache:
                    imgs.append(back_cache[url].copy())
                    continue
                async with session.get(url, timeout=5) as r:
                    if r.status == 200:
                        data = await r.read()
                        with Image.open(BytesIO(data)) as temp:
                            img = temp.convert("RGBA").resize((300, 420), Image.Resampling.LANCZOS)
                            imgs.append(img)
                            if len(back_cache) < 50: back_cache[url] = img.copy()
            
            canvas = Image.new("RGBA", (len(imgs)*300, 420))
            for i, img in enumerate(imgs):
                canvas.paste(img, (i*300, 0))
                img.close()
            
            buf = BytesIO()
            canvas.save(buf, "PNG", optimize=True)
            buf.seek(0)
            return buf
        finally:
            imgs.clear()
            gc.collect()

# ======================
# 🎒 INVENTORY PAGINATION
# ======================
class InventoryView(discord.ui.View):
    def __init__(self, pages, user_id):
        super().__init__(timeout=120)
        self.pages, self.page, self.user_id = pages, 0, user_id

    async def update(self, interaction):
        embed = discord.Embed(title=self.pages[self.page]["title"], description=self.pages[self.page]["content"], color=0x2b2d31)
        embed.set_footer(text=f"Page {self.page+1}/{len(self.pages)}")
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="◀")
    async def prev(self, interaction, button):
        if interaction.user.id != self.user_id: return
        if self.page > 0: self.page -= 1
        await self.update(interaction)

    @discord.ui.button(label="▶")
    async def next(self, interaction, button):
        if interaction.user.id != self.user_id: return
        if self.page < len(self.pages)-1: self.page += 1
        await self.update(interaction)

# ======================
# 🎴 DROP SYSTEM
# ======================
class DropView(discord.ui.View):
    def __init__(self, cards_list):
        super().__init__(timeout=60)
        self.cards, self.claimed = cards_list, [False]*3

    async def handle_claim(self, interaction, idx):
        if self.claimed[idx]: return await interaction.response.send_message("✧ taken", ephemeral=True)
        
        self.claimed[idx] = True
        for child in self.children: child.disabled = True
        await interaction.response.edit_message(view=self)

        card = self.cards[idx]
        await users.update_one({"id": interaction.user.id}, {"$inc": {f"cards.{card['card_code']}": 1}}, upsert=True)
        
        embed = discord.Embed(title=f"✧ {card['name']} ✧", description=f"{card['group']} • {card['rarity'].title()}", color=0x2b2d31)
        embed.set_image(url=card["image_url"])
        await interaction.followup.send(content=f"{interaction.user.mention} claimed:", embed=embed)

    @discord.ui.button(label="1")
    async def b1(self, i, b): await self.handle_claim(i, 0)
    @discord.ui.button(label="2")
    async def b2(self, i, b): await self.handle_claim(i, 1)
    @discord.ui.button(label="3")
    async def b3(self, i, b): await self.handle_claim(i, 2)

@tree.command(name="drop", description="✧ summon cards")
async def drop(interaction: discord.Interaction):
    await interaction.response.defer()
    
    chosen = [await get_card() for _ in range(3)]
    if None in chosen: return await interaction.followup.send("✧ no cards found")

    backs = [await get_back(c) for c in chosen]
    img_buf = await merge_images(backs)
    
    embed = discord.Embed(title="✧ ethereal descent ✧", color=0x2b2d31)
    embed.set_image(url="attachment://drop.png")
    
    await interaction.followup.send(file=discord.File(img_buf, "drop.png"), embed=embed, view=DropView(chosen))

# ======================
# 🎒 INVENTORY
# ======================
@tree.command(name="inventory")
async def inventory(interaction: discord.Interaction, user: discord.User = None):
    await interaction.response.defer()
    target = user or interaction.user
    data = await users.find_one({"id": target.id})
    if not data or "cards" not in data: return await interaction.followup.send("✧ empty")

    items = []
    for code, count in data["cards"].items():
        if count <= 0: continue
        c = await cards.find_one({"card_code": code})
        if c:
            icon = RARITY_ICONS.get(c["rarity"], "✧")
            items.append(f"{icon} **{c['name']}** • {c['card_code']} (×{count})")

    if not items: return await interaction.followup.send("✧ empty")
    
    pages = [{"title": f"{target.name}'s items", "content": "\n".join(items[i:i+8])} for i in range(0, len(items), 8)]
    await interaction.followup.send(embed=discord.Embed(title=pages[0]["title"], description=pages[0]["content"], color=0x2b2d31), view=InventoryView(pages, interaction.user.id))

# ======================
# 🔒 STAFF COMMANDS
# ======================
@tree.command(name="add_card")
@app_commands.choices(rarity=RARITY_CHOICES)
async def add_card(interaction: discord.Interaction, name:str, group:str, rarity:app_commands.Choice[str], card_code:str, image_url:str, droppable:bool):
    if not is_staff(interaction.user.id): return
    await cards.insert_one({"name":name, "group":group.lower(), "rarity":rarity.value, "card_code":card_code, "image_url":image_url, "droppable":droppable})
    await interaction.response.send_message("✧ card added")

@tree.command(name="daily")
async def daily(interaction: discord.Interaction):
    uid = interaction.user.id
    user = await users.find_one({"id": uid})
    now = int(time.time())
    if user and now - user.get("last_daily", 0) < DAILY_CD:
        return await interaction.response.send_message("✧ already claimed", ephemeral=True)
    
    card = await get_card()
    await users.update_one({"id": uid}, {"$set": {"last_daily": now}, "$inc": {"currency": 50, f"cards.{card['card_code']}": 1}}, upsert=True)
    await interaction.response.send_message(f"✧ blessed! +50 {CURRENCY} and {card['name']}")

# ======================
# 🚀 STARTUP
# ======================
@bot.event
async def on_ready():
    await tree.sync()
    print(f"Logged in as {bot.user}")

bot.run(TOKEN)


