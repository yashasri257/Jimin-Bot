
import disnake
from disnake.ext import commands
import sqlite3, random, time, asyncio, os
from PIL import Image
import requests
from io import BytesIO

intents = disnake.Intents.default()
intents.message_content = True
bot = commands.InteractionBot(intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

intents = disnake.Intents.default()

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
    "whisper": {"color": 0xCFEFFF, "icon": "https://cdn.discordapp.com/attachments/1487054242244984957/1487872174323667014/Untitled13_20260329154525.png?ex=69cab871&is=69c966f1&hm=9c1f374c765909f96ebc1f8ba261557d46acc18878fc057ec8b9b8c6a54e2c64&"},
    "cherub": {"color": 0xF8C8DC, "icon": "https://cdn.discordapp.com/attachments/1487054242244984957/1487872287729258739/Untitled13_20260329155942.png?ex=69cab88c&is=69c9670c&hm=f0da840eb57c1f6d02a756b262cd3ad01be0fabdd24569f6a9ec0f9ec80549d6&"},
    "siren": {"color": 0x5DADE2, "icon": "https://cdn.discordapp.com/attachments/1487054242244984957/1487872389701308426/Untitled13_20260329183750.png?ex=69cab8a5&is=69c96725&hm=14218d268f4974dadcbbca64d59aade4124e468180ac4f2920d7e3a8d6fafeeb&"},
    "enthrall": {"color": 0xFF7043, "icon": "https://cdn.discordapp.com/attachments/1487054242244984957/1487880470644523149/Untitled13_20260329235353.png?ex=69cac02b&is=69c96eab&hm=6ff8d037207418ae911b67080c9fa5295ef8a7232139c24139475f948ad30361&"},
    "devotion": {"color": 0x8B0000, "icon": "https://cdn.discordapp.com/attachments/1487054242244984957/1487880569500209243/Untitled13_20260329185342.png?ex=69cac043&is=69c96ec3&hm=72cc6f83ae0358cfb0b81e05dc9c63d75a7eef6737c25f37599eff8df159567f&"},
    "fallen": {"color": 0x000000, "icon": "https://cdn.discordapp.com/attachments/1487054242244984957/1487881032261828710/Untitled13_20260329194919.png?ex=69cac0b1&is=69c96f31&hm=44507983cf6f3753f15a6dcf0b18213a9f2eb959912255287fe5287a3f7412b7&"},
    "eclipse": {"color": 0x9CAF88, "icon": "https://cdn.discordapp.com/attachments/1487054242244984957/1487881187421720797/Untitled13_20260329001614.png?ex=69cac0d6&is=69c96f56&hm=8597e7b07d40ca54c4a5d0aef94ec64c110a868379adf6bafd630f8b0c054b9c&"},
    "velour": {"color": 0x8E44AD, "icon": "https://cdn.discordapp.com/attachments/1487054242244984957/1487523307971543131/Untitled13_20260329001614.png?ex=69ca1c49&is=69c8cac9&hm=614614a3e0969c7235f53ce225abceb39685d50621cc7f0f3e5d03b646887f77&"},
    "sanctum": {"color": 0xFFF4B3, "icon": "https://cdn.discordapp.com/attachments/1487054242244984957/1487881249191235604/Untitled13_20260329231514.png?ex=69cac0e5&is=69c96f65&hm=873814e6edbcdde7d54441af093618c16ef007c511d2b5aa09d934078258096a&"},
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
# 🖼 IMAGE
# =========================
def create_image(cards):
    imgs = []
    for card in cards:
      #  r = requests.get(card[5])
        img = Image.open(BytesIO(r.content)).resize((250,350))
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
        await inter.response.send_message("🐽 Code exists, dumbass!", ephemeral=True)

# =========================
# ❌ DELETE CARD
# =========================
@bot.slash_command()
async def delcard(inter, card_code:str):
    c.execute("DELETE FROM cards WHERE code=?", (card_code.lower(),))
    conn.commit()
    await inter.response.send_message(f" Deleted `{card_code}`")

# =========================
# 🔍 VIEW
# =========================
@bot.slash_command()
async def view(inter, card_code:str):
    c.execute("SELECT * FROM cards WHERE code=?", (card_code.lower(),))
    card = c.fetchone()

    if not card:
        return await inter.response.send_message("Card not found. Clean your glasses!", ephemeral=True)

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

    embed.set_thumbnail(url=data["icon"])
    embed.set_image(url=card[5])
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
            return await inter.response.send_message("⏳ wait", ephemeral=True)

        if uid in claim_cd and now < claim_cd[uid]:
            return await inter.response.send_message("⏳ cooldown", ephemeral=True)

        if self.claimed[i]:
            return await inter.response.send_message("❌ taken", ephemeral=True)

        claim_cd[uid] = now + 120
        self.claimed[i] = uid

        c.execute("INSERT INTO users VALUES (?,?)", (str(uid), self.cards[i][0]))
        conn.commit()

        await inter.response.send_message("✓ claimed", ephemeral=True)

    @disnake.ui.button(label="1")
    async def b1(self, b, i): await self.claim(i,0)

    @disnake.ui.button(label="2")
    async def b2(self, b, i): await self.claim(i,1)

    @disnake.ui.button(label="3")
    async def b3(self, b, i): await self.claim(i,2)

@bot.slash_command()
async def drop(inter):
    uid = inter.user.id
    now = time.time()

    if uid in drop_cd and now < drop_cd[uid]:
        return await inter.response.send_message("⏳ cooldown, calm down.", ephemeral=True)

    drop_cd[uid] = now + 300

    cards = [pick_card() for _ in range(3)]
    img = create_image(cards)

    file = disnake.File(img, filename="drop.png")
    embed = disnake.Embed(title="🎴 Drop")
    embed.set_image(url="attachment://drop.png")

    view = DropView(cards, uid)

    await inter.response.send_message(embed=embed, file=file, view=view)

# =========================
# 📦 INVENTORY PAGINATION
# =========================
class InventoryView(disnake.ui.View):
    def __init__(self, data, user):
        super().__init__(timeout=60)
        self.data = data
        self.page = 0
        self.user = user

    def get_embed(self):
        start = self.page * 10
        chunk = self.data[start:start+10]

        text = ""
        for r in chunk:
            text += f"{r[0]} ({r[1]}) - {r[2]} x{r[4]} `{r[3]}`\n"

        embed = disnake.Embed(title="📦 Inventory", description=text)
        embed.set_footer(text=f"Page {self.page+1}/{(len(self.data)-1)//10 +1}")
        return embed

    @disnake.ui.button(label="⬅️")
    async def prev(self, b, inter):
        if inter.user != self.user: return
        if self.page > 0:
            self.page -= 1
        await inter.response.edit_message(embed=self.get_embed(), view=self)

    @disnake.ui.button(label="➡️")
    async def next(self, b, inter):
        if inter.user != self.user: return
        if (self.page+1)*10 < len(self.data):
            self.page += 1
        await inter.response.edit_message(embed=self.get_embed(), view=self)

@bot.slash_command()
async def inventory(
    inter,
    user: disnake.User=None,
    name:str=None,
    group:str=None,
    rarity:str=commands.Param(choices=[r.title() for r in RARITIES], default=None),
    dupes:bool=None,
    era:str=None
):
    uid = str(user.id if user else inter.user.id)

    query = """SELECT cards.name, cards.group_name, cards.rarity, cards.code, COUNT(*)
               FROM users JOIN cards ON users.card_code = cards.code
               WHERE users.user_id=?"""
    params = [uid]

    if name:
        query += " AND cards.name LIKE ?"
        params.append(f"%{name}%")
    if group:
        query += " AND cards.group_name LIKE ?"
        params.append(f"%{group}%")
    if rarity:
        query += " AND cards.rarity=?"
        params.append(rarity.lower())
    if era:
        query += " AND cards.era LIKE ?"
        params.append(f"%{era}%")

    query += " GROUP BY cards.code"

    if dupes:
        query += " HAVING COUNT(*) > 1"

    c.execute(query, params)
    results = c.fetchall()

    if not results:
        return await inter.response.send_message("No cards found")

    view = InventoryView(results, inter.user)
    await inter.response.send_message(embed=view.get_embed(), view=view)

# =========================
bot.run(os.getenv("TOKEN"))
