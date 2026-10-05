"""The town: map layout, buildings, collision and things you can talk to.

Map legend:
  .  grass        ,  flowers      =  dirt path    #  cobblestone plaza
  ~  pond         T  tree         f  fence        L  lamp post
  F  fountain     s  sign         @  start        1-5  building tiles
"""

MAP = [
    "TTTTTTTTTTTTTTTTTTTTTTTT",
    "T..,..T.fffffff...,..T.T",
    "T.1111..f,,,,,f..2222..T",
    "T.1111..f,,,,,f..2222.TT",
    "T.1111..fff.fff..2222..T",
    "T..=..,....=.s....=....T",
    "T..================....T",
    "T.....T....=......T....T",
    "T.......L#####L.,......T",
    "T.3333..#######..~~~~..T",
    "T.3333==#######.~~~~~..T",
    "T.3333..###F###.~~~~~~.T",
    "T.3333..#######..~~~~..T",
    "T.,.....#######...~~...T",
    "T...T...L#####L........T",
    "T..........=........T..T",
    "T.55555....=....4444...T",
    "T.55555=====....4444...T",
    "T.55555....=....4444.,.T",
    "T.55555....=....4444...T",
    "T..........@======.....T",
    "T...T......=......,....T",
    "T..,.......=..........TT",
    "TTTTTTTTTTTTTTTTTTTTTTTT",
]

GROUND = {".": "grass", ",": "flowers", "=": "path", "#": "plaza", "~": "water",
          "T": "grass", "f": "grass", "s": "grass", "L": "plaza", "F": "plaza", "@": "path"}
FEATURES = {"T": "tree", "f": "fence", "L": "lamp", "F": "fountain", "s": "sign"}

WALL_H = 7
ROOF_EDGE = 3
ROOF_STEP = 3

# door_face "y" puts the door on the +y wall (screen lower-left), "x" on the +x wall.
BUILDINGS = {
    "1": dict(name="Town Hall", wall=(228, 214, 182), roof=(176, 62, 52),
              door=(3, 4), door_face="y", chimney=(4, 3),
              line="Town Hall. A note on the door: 'Back in 5 minutes.' It was posted three hours ago."),
    "2": dict(name="Library", wall=(196, 206, 214), roof=(58, 110, 150),
              door=(18, 4), door_face="y", chimney=None,
              line="The Library. Every single book is titled 'Attention Is All You Need'."),
    "3": dict(name="Cottage", wall=(238, 226, 160), roof=(74, 128, 74),
              door=(5, 10), door_face="x", chimney=(3, 10),
              line="A cozy cottage. Someone inside is snoring in perfect 4/4 time."),
    "4": dict(name="Inn", wall=(230, 190, 170), roof=(120, 80, 140),
              door=(17, 19), door_face="y", chimney=None,
              line="The Sleepy Transformer Inn. Checkout is whenever you run out of context."),
    "5": dict(name="Bakery", wall=(170, 120, 84), roof=(214, 120, 60),
              door=(6, 17), door_face="x", chimney=(3, 17),
              line="The Bakery smells amazing. A sign says: 'No crumbs on the keyboard.'"),
}

SIGNS = {
    (13, 5): "NORTH ROAD - Garden up the path, Plaza down it. Please do not hallucinate on the grass.",
}

FOUNTAIN_LINE = "The fountain burbles. A coin at the bottom reads 'In Weights We Trust'."
POND_LINE = "The pond is very still. Something with a 200k context window lurks below."

NPCS = [
    dict(role="Mayor", pos=(10, 13), hair=(90, 90, 96), skin=(236, 196, 160),
         shirt=(60, 70, 140), pants=(40, 40, 50), lines=[
             "Welcome to Tokenville, little one!",
             "Our motto: helpful, harmless, honest... and home by six.",
             "The fountain runs on pure context. Please don't drink it.",
         ]),
    dict(role="Baker", pos=(8, 18), hair=(240, 240, 240), skin=(200, 150, 110),
         shirt=(245, 245, 235), pants=(110, 80, 60), lines=[
             "Fresh sourdough, straight out of the oven!",
             "A croissant for you? ...Do you have a mouth?",
             "I knead dough, you need tokens. We're not so different.",
         ]),
    dict(role="Fisher", pos=(16, 13), hair=(120, 70, 40), skin=(230, 185, 150),
         shirt=(200, 170, 60), pants=(60, 80, 60), lines=[
             "Shh. You'll scare the bass.",
             "Caught a fish so big here once I had to summarize it to fit the bucket.",
             "Some days they bite. Some days they hallucinate.",
         ]),
    dict(role="Gardener", pos=(10, 2), hair=(60, 40, 30), skin=(170, 120, 90),
         shirt=(90, 150, 80), pants=(90, 70, 50), lines=[
             "These tulips took three whole epochs to bloom.",
             "Careful - the roses have attention heads. Very thorny.",
             "Water, sunlight, gradient descent. That's the whole secret.",
         ]),
    dict(role="Kid", pos=(14, 21), hair=(230, 180, 60), skin=(240, 205, 175),
         shirt=(220, 70, 90), pants=(60, 90, 160), lines=[
             "Are you a crab? You look like a crab.",
             "Can you do my homework? ...Kidding. Unless?",
             "Tag, you're it! ...You're kinda slow, huh.",
         ]),
]


class Building:
    def __init__(self, bid, tiles, spec):
        self.id = bid
        xs = [x for x, _ in tiles]
        ys = [y for _, y in tiles]
        self.x0, self.x1, self.y0, self.y1 = min(xs), max(xs), min(ys), max(ys)
        self.name = spec["name"]
        self.wall = spec["wall"]
        self.roof = spec["roof"]
        self.door = spec["door"]
        self.door_face = spec["door_face"]
        self.chimney = spec["chimney"]
        self.line = spec["line"]

    def contains(self, x, y):
        return self.x0 <= x <= self.x1 and self.y0 <= y <= self.y1

    def height_at(self, x, y):
        """Total height in pixels: walls plus a stepped gable roof."""
        if self.x1 - self.x0 >= self.y1 - self.y0:
            d = min(y - self.y0, self.y1 - y)
        else:
            d = min(x - self.x0, self.x1 - x)
        return WALL_H + ROOF_EDGE + ROOF_STEP * d

    def door_outside(self):
        x, y = self.door
        return (x, y + 1) if self.door_face == "y" else (x + 1, y)


class World:
    def __init__(self, rows=MAP, buildings=BUILDINGS):
        self.width = len(rows[0])
        self.height = len(rows)
        self._ground = {}
        self._feature = {}
        self._building = {}
        building_tiles = {}
        for y, row in enumerate(rows):
            for x, ch in enumerate(row):
                if ch.isdigit():
                    self._ground[(x, y)] = "grass"
                    building_tiles.setdefault(ch, []).append((x, y))
                    continue
                self._ground[(x, y)] = GROUND[ch]
                if ch in FEATURES:
                    self._feature[(x, y)] = FEATURES[ch]
                if ch == "@":
                    self.start = (x, y)
        self.buildings = {}
        for bid, tiles in building_tiles.items():
            b = Building(bid, tiles, buildings[bid])
            self.buildings[bid] = b
            for t in tiles:
                self._building[t] = b

    def in_bounds(self, x, y):
        return 0 <= x < self.width and 0 <= y < self.height

    def ground(self, x, y):
        return self._ground.get((x, y))

    def feature(self, x, y):
        return self._feature.get((x, y))

    def building_at(self, x, y):
        return self._building.get((x, y))

    def blocked(self, x, y):
        if not self.in_bounds(x, y):
            return True
        return (self._ground[(x, y)] == "water" or (x, y) in self._feature
                or (x, y) in self._building)

    def interaction_at(self, x, y):
        if (x, y) in SIGNS:
            return SIGNS[(x, y)]
        b = self.building_at(x, y)
        if b and b.door == (x, y):
            return b.line
        if self.feature(x, y) == "fountain":
            return FOUNTAIN_LINE
        if self.ground(x, y) == "water":
            return POND_LINE
        return None


def load():
    return World()
