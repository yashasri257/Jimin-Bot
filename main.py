import disnake
from disnake.ext import commands
import sqlite3, random, time, os
from PIL import Image
import requests
from io import BytesIO

# =========================
# 🤖 BOT SETUP
# =========================
intents = disnake.Intents.default()
intents.message_content = True
bot = commands.InteractionBot(intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

# =========================
# 🗄 DATABASE
# =========================
conn = sqlite3.connect("bot.db")
c = conn.cursor()

c.execute("""CREATE TABLE IF NOT EXISTS cards (
    code TEXT PRIMARY KEY,
    name TEXT,
    group_name TEXT,
    rarity TEXT,
    era TEXT,
    image TEXT,
    droppable INTEGER
)""")

c.execute("""CREATE TABLE IF NOT EXISTS users (
    user_id TEXT,
    card_code TEXT
)""")

conn.commit()

# =========================
# 🎨 RARITY CONFIG
# =========================
RARITY_INFO = {
    "whisper": {"color": 0xCFEFFF, "icon": "https://i.postimg.cc/BvmwPc6N/Untitled13_20260329154525.png"},
    "cherub": {"color": 0xF8C8DC, "icon": "https://i.postimg.cc/bvmFSHJV/Untitled13_20260329155942.png"},
    "siren": {"color": 0x5DADE2, "icon": "https://i.postimg.cc/Lsx0gBXw/Untitled13_20260329183750.png"},
    "enthrall": {"color": 0xFF7043, "icon": "https://i.postimg.cc/KY0s3rzW/Untitled13_20260329235353.png"},
    "devotion": {"color": 0x8B0000, "icon": "https://i.postimg.cc/BvmwPc6V/Untitled13_20260329185342.png"},
    "fallen": {"color": 0x000000, "icon": "https://i.postimg.cc/N0dP27FB/Untitled13_20260329194919.png"},
    "eclipse": {"color": 0x9CAF88, "icon": "https://i.postimg.cc/7LKQJMhq/Untitled13_20260329201615.png"},
    "velour": {"color": 0x8E44AD, "icon": "https://i.postimg.cc/XvsDBcqq/Untitled13_20260329001614.png"},
    "sanctum": {"color": 0xFFF4B3, "icon": "https://i.postimg.cc/Lsx0gB58/Untitled13_20260329231514.png"},
}

RARITIES = list(RARITY_INFO.keys())

# =========================
# 🎲 DROP LOGIC
# =========================
def roll_rarity():
    roll = random.randint(1,100)
    if roll <= 40: return "whisper"
    elif roll <= 65: return "cherub"
    elif roll <= 85: return "siren"
    elif roll <= 95: return "enthrall"
    else: return "devotion"

def pick_card():
    while True:
        rarity = roll_rarity()
        c.execute("SELECT * FROM cards WHERE rarity=? AND droppable=1", (rarity,))
        cards = c.fetchall()
        if cards:
            return random.choice(cards)

# =========================
# 🖼 SAFE IMAGE CREATION
# =========================
def create_image(cards):
    imgs = []

    for card in cards:
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            r = requests.get(card[5], headers=headers, timeout=5)

            if "image" not in r.headers.get("Content-Type", ""):
                raise Exception("Not image")

            img = Image.open(BytesIO(r.content)).resize((250,350))
        except:
            img = Image.new("RGB", (250,350), (30,30,30))

        imgs.append(img)

    canvas = Image.new("RGB", (820,400), (20,20,20))

    for i, img in enumerate(imgs):
        canvas.paste(img, (i*270+20, 20))

    path = "drop.png"
    canvas.save(path)
    return path

# =========================
# ➕ ADD CARD
# =========================
@bot.slash_command()
async def addcard(inter, name:str, group:str,
                  rarity:str=commands.Param(choices=[r.title() for r in RARITIES]),
                  card_code:str="",
                  droppable:bool=True,
                  image:str="",
                  era:str=""):

    try:
        c.execute("INSERT INTO cards VALUES (?,?,?,?,?,?,?)",
                  (card_code.lower(), name, group, rarity.lower(), era, image, int(droppable)))
        conn.commit()
        await inter.response.send_message(f"✓ Added `{card_code}`")
    except:
        await inter.response.send_message("Code already exists", ephemeral=True)

# =========================
# ❌ DELETE CARD
# =========================
@bot.slash_command()
async def delcard(inter, card_code:str):
    c.execute("DELETE FROM cards WHERE code=?", (card_code.lower(),))
    conn.commit()
    await inter.response.send_message(f"Deleted `{card_code}`")

# =========================
# 🔍 VIEW
# =========================
@bot.slash_command()
async def view(inter, card_code:str):
    c.execute("SELECT * FROM cards WHERE code=?", (card_code.lower(),))
    card = c.fetchone()

    if not card:
        return await inter.response.send_message("Card not found", ephemeral=True)

    data = RARITY_INFO[card[3]]

    c.execute("SELECT COUNT(*) FROM users WHERE user_id=? AND card_code=?",
              (str(inter.user.id), card[0]))
    count = c.fetchone()[0]

    embed = disnake.Embed(title=card[1], color=data["color"])
    embed.add_field(name="Group", value=card[2])
    embed.add_field(name="Rarity", value=card[3].title())
    embed.add_field(name="Card Code", value=f"`{card[0]}`")

    if card[4]:
        embed.add_field(name="Era", value=card[4])

    embed.add_field(name="Image", value=f"[Click to view]({card[5]})", inline=False)
    embed.set_footer(text=f"You own {count} copies")

    await inter.response.send_message(embed=embed)

# =========================
# 🎴 DROP
# =========================
drop_cd = {}
claim_cd = {}

class DropView(disnake.ui.View):
    def __init__(self, cards, dropper):
        super().__init__(timeout=30)
        self.cards = cards
        self.claimed = [None,None,None]
        self.dropper = dropper
        self.start = time.time()

    async def claim(self, inter, i):
        uid = inter.user.id
        now = time.time()

        if uid != self.dropper and now - self.start < 30:
            return await inter.response.send_message("Wait 30s", ephemeral=True)

        if uid in claim_cd and now < claim_cd[uid]:
            return await inter.response.send_message("On cooldown", ephemeral=True)

        if self.claimed[i]:
            return await inter.response.send_message("Taken", ephemeral=True)

        claim_cd[uid] = now + 120
        self.claimed[i] = uid

        c.execute("INSERT INTO users VALUES (?,?)", (str(uid), self.cards[i][0]))
        conn.commit()

        await inter.response.send_message("Claimed!", ephemeral=True)

    @disnake.ui.button(label="1")
    async def b1(self, b, inter): await self.claim(inter,0)

    @disnake.ui.button(label="2")
    async def b2(self, b, inter): await self.claim(inter,1)

    @disnake.ui.button(label="3")
    async def b3(self, b, inter): await self.claim(inter,2)


@bot.slash_command()
async def drop(inter):
    uid = inter.user.id
    now = time.time()

    if uid in drop_cd and now < drop_cd[uid]:
        return await inter.response.send_message("Cooldown active", ephemeral=True)

    drop_cd[uid] = now + 300

    cards = [pick_card() for _ in range(3)]

    embed = disnake.Embed(title="🎴 Drop")

    embed.add_field(
        name="Card 1",
        value=f"{cards[0][1]} ({cards[0][3]})\n[View Image]({cards[0][5]})",
        inline=True
    )
    embed.add_field(
        name="Card 2",
        value=f"{cards[1][1]} ({cards[1][3]})\n[View Image]({cards[1][5]})",
        inline=True
    )
    embed.add_field(
        name="Card 3",
        value=f"{cards[2][1]} ({cards[2][3]})\n[View Image]({cards[2][5]})",
        inline=True
    )

    view = DropView(cards, uid)

    await inter.response.send_message(embed=embed, view=view)

# =========================
bot.run(os.getenv("TOKEN"))
