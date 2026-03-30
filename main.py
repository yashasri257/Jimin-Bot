import disnake
from disnake.ext import commands
import sqlite3, random, os

# =========================
# BOT SETUP
# =========================
intents = disnake.Intents.default()
intents.message_content = True
bot = commands.InteractionBot(intents=intents)

# =========================
# DATABASE
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
# RARITY CONFIG
# =========================
RARITY_INFO = {
    "whisper": {"color": 0xCFEFFF, "icon": "https://cdn.discordapp.com/attachments/1487054242244984957/1487872174323667014/Untitled13_20260329154525.png?ex=69cb6131&is=69ca0fb1&hm=42bc46278fb5827e815388ab95a062471255e7ad786310d94de4b28b95b9c660&"},
    "cherub": {"color": 0xF8C8DC, "icon": "https://cdn.discordapp.com/attachments/1487054242244984957/1487872287729258739/Untitled13_20260329155942.png?ex=69cb614c&is=69ca0fcc&hm=d17e115232ef7822eed9dfb6cdec44b167ba4895b562e81fe467a077c3938494&"},
    "siren": {"color": 0x5DADE2, "icon": "https://cdn.discordapp.com/attachments/1487054242244984957/1487872389701308426/Untitled13_20260329183750.png?ex=69cb6165&is=69ca0fe5&hm=d8596dc369f8a16c1364535639c0769941422fc925a9a56cab158d46a3c74eba&"},
    "enthrall": {"color": 0xE67E22, "icon": "https://cdn.discordapp.com/attachments/1487054242244984957/1487880470644523149/Untitled13_20260329235353.png?ex=69cb68eb&is=69ca176b&hm=17e1546449af7b9da62db6c78d1ab2ad3d44cc591758226b5e9c8fa86cd6d12d&"},
    "devotion": {"color": 0x922B21, "icon": "https://cdn.discordapp.com/attachments/1487054242244984957/1487880569500209243/Untitled13_20260329185342.png?ex=69cb6903&is=69ca1783&hm=aad1527f0ebec927e18a88130bbb33f5c188f7550f193abc0e0988fd48776a7c&"},
    "fallen": {"color": 0x000000, "icon": "https://cdn.discordapp.com/attachments/1487054242244984957/1487881032261828710/Untitled13_20260329194919.png?ex=69cb6971&is=69ca17f1&hm=134760bf3eb1110d4d08d51c7b973286efaf4f9b4050c61e08675c92ad2cdaf8&"},  # NEW
    "eclipse": {"color": 0x6B8E23, "icon": "https://cdn.discordapp.com/attachments/1487054242244984957/1487881115988394037/Untitled13_20260329201615.png?ex=69cb6985&is=69ca1805&hm=25b903330ce56bd2428c34cbe8ff190a2b60078a9b0c4549b3cc760801affe49&"},
    "velour": {"color": 0x8E44AD, "icon": "https://cdn.discordapp.com/attachments/1487054242244984957/1487881187421720797/Untitled13_20260329001614.png?ex=69cb6996&is=69ca1816&hm=49e4402096b9bdfc92c165154ae8517f587f69d2a416ab6a768b739367586c54&"},
    "sanctum": {"color": 0xD4AC0D, "icon": "https://cdn.discordapp.com/attachments/1487054242244984957/1487881249191235604/Untitled13_20260329231514.png?ex=69cb69a5&is=69ca1825&hm=f7a8d8463820636aec15cfb25c2dc865628ca99a7d95642474cce9325078fa51&"},
}

RARITIES = list(RARITY_INFO.keys())

# =========================
# DROP LOGIC (NO FALLEN)
# =========================
def roll_rarity():
    roll = random.randint(1, 100)
    if roll <= 35: return "whisper"
    elif roll <= 65: return "cherub"
    elif roll <= 82: return "siren"
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
# 🔥 FALLEN REWARD CHECK
# =========================
def check_fallen_unlock(user_id, group_name):
    # total non-fallen cards in that group
    c.execute("""
    SELECT COUNT(*) FROM cards
    WHERE group_name=? AND rarity!='fallen'
    """, (group_name,))
    total = c.fetchone()[0]

    # how many user owns
    c.execute("""
    SELECT COUNT(DISTINCT card_code)
    FROM users
    JOIN cards ON users.card_code = cards.code
    WHERE users.user_id=? AND cards.group_name=? AND cards.rarity!='fallen'
    """, (user_id, group_name))
    owned = c.fetchone()[0]

    if owned == total and total > 0:
        # give all fallen cards of that group
        c.execute("""
        SELECT code FROM cards
        WHERE group_name=? AND rarity='fallen'
        """, (group_name,))
        fallen_cards = c.fetchall()

        for fc in fallen_cards:
            c.execute("SELECT 1 FROM users WHERE user_id=? AND card_code=?", (user_id, fc[0]))
            if not c.fetchone():
                c.execute("INSERT INTO users VALUES (?,?)", (user_id, fc[0]))

        conn.commit()
        return True

    return False

# =========================
# ADD CARD
# =========================
@bot.slash_command()
async def addcard(
    inter,
    name: str,
    group: str,
    rarity: str = commands.Param(choices=[r.title() for r in RARITIES]),
    card_code: str = "",
    droppable: bool = True,
    image: str = "",
    era: str = ""
):
    try:
        c.execute("INSERT INTO cards VALUES (?,?,?,?,?,?,?)",
                  (card_code.lower(), name, group, rarity.lower(), era, image, int(droppable)))
        conn.commit()
        await inter.response.send_message(f"Added `{card_code}`")
    except:
        await inter.response.send_message("Card code already exists", ephemeral=True)

# =========================
# VIEW CARD
# =========================
@bot.slash_command()
async def view(inter, card_code: str):
    c.execute("SELECT * FROM cards WHERE code=?", (card_code.lower(),))
    card = c.fetchone()

    if not card:
        return await inter.response.send_message("Card not found", ephemeral=True)

    rarity = RARITY_INFO[card[3]]

    embed = disnake.Embed(title=card[1], color=rarity["color"])

    embed.add_field(name="Group", value=card[2])
    embed.add_field(name="Rarity", value=card[3].title())
    embed.add_field(name="Card Code", value=f"`{card[0]}`")

    if card[4]:
        embed.add_field(name="Era", value=card[4])

    embed.set_thumbnail(url=rarity["icon"])
    embed.set_image(url=card[5])

    await inter.response.send_message(embed=embed)

# =========================
# DROP VIEW
# =========================
class DropView(disnake.ui.View):
    def __init__(self, cards):
        super().__init__(timeout=30)
        self.cards = cards
        self.claimed = [False, False, False]

    async def claim(self, inter, index):
        if self.claimed[index]:
            return await inter.response.send_message("Already claimed", ephemeral=True)

        self.claimed[index] = True

        user_id = str(inter.user.id)
        card = self.cards[index]

        c.execute("INSERT INTO users VALUES (?,?)", (user_id, card[0]))
        conn.commit()

        # check fallen unlock
        unlocked = check_fallen_unlock(user_id, card[2])

        msg = f"Claimed {card[1]}"
        if unlocked:
            msg += "\nUnlocked Fallen cards for this group."

        await inter.response.send_message(msg, ephemeral=True)

    @disnake.ui.button(label="1")
    async def b1(self, button, inter):
        await self.claim(inter, 0)

    @disnake.ui.button(label="2")
    async def b2(self, button, inter):
        await self.claim(inter, 1)

    @disnake.ui.button(label="3")
    async def b3(self, button, inter):
        await self.claim(inter, 2)

# =========================
# DROP
# =========================
@bot.slash_command()
async def drop(inter):
    cards = [pick_card() for _ in range(3)]

    embed = disnake.Embed(title="Drop")

    for card in cards:
        embed.add_field(
            name=card[1],
            value=f"{card[2]}\n{card[3].title()}",
            inline=True
        )

    view = DropView(cards)

    await inter.response.send_message(embed=embed, view=view)

# =========================
# INVENTORY
# =========================
@bot.slash_command()
async def inventory(inter, user: disnake.User = None):
    uid = str(user.id if user else inter.user.id)

    c.execute("""
    SELECT cards.name, cards.group_name, cards.rarity, COUNT(*)
    FROM users
    JOIN cards ON users.card_code = cards.code
    WHERE users.user_id=?
    GROUP BY cards.code
    """, (uid,))

    data = c.fetchall()

    if not data:
        return await inter.response.send_message("Empty inventory")

    text = ""
    for row in data:
        text += f"{row[0]} ({row[1]}) - {row[2]} x{row[3]}\n"

    embed = disnake.Embed(title="Inventory", description=text)
    await inter.response.send_message(embed=embed)

# =========================
# START
# =========================
bot.run(os.getenv("TOKEN"))
  
