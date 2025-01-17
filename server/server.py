#!/bin/env python3

import os
import json
import threading
from dataclasses import dataclass, field
import textwrap
# import collections  # for defaultdict behavior

import net_server
import net_common
import common
import util

# from players import Player

K = common.K
Mode = net_server.Mode
Message = net_server.Message

# fake data - make sure keys match those in Room class
# these are nice room descriptions, but not sure where they can be used
"""
roomsData = [
    {K.number: 1,
     K.name: 'Brookdale',
     K.desc: "You find yourself in the lovely upper left corner of the map. "
             "A small town nestles in the valley, a day's travel most likely. "
             "A dirt path leads south, and a babbling brook flows eastwards.",
     K.exits: {'s': 3, 'e': 2},
     K.monster: 0,
     K.item: 1,
     K.weapon: 1,
     K.food: 1,
     K.alignment: 'Claw'},

    {K.number: 2,
     K.name: 'Suntop Lookout',
     K.desc: "The sun shines brightly overhead. A dirt path meanders eastwards "
             "towards more tranquil scenery. A foreboding forest of dark, evil "
             "trees looms to the south.",
     K.exits: {'s': 4, 'w': 1},
     K.monster: 0,
     K.item: 1,
     K.weapon: 1,
     K.food: 1,
     K.alignment: 'Sword'},

    {K.number: 3,
     K.name: 'Near Castle',
     K.desc: "Behold, the castle Brackenwald can be spied beyond some "
             "rolling hills. Eastwards is the reputedly haunted forest.",
     K.exits: {'n': 1, 'e': 4},
     K.monster: 0,
     K.item: 1,
     K.weapon: 1,
     K.food: 1,
     K.alignment: 'Fist'},

    {K.number: 4,
     K.name: 'Dark Forest',
     K.desc: "The sun overhead filters dimly through twisted branches. There is "
             "a rusty sword on the ground--looks like you're going to need it.",
     K.exits: {'n': 2, 'w': 3},
     K.monster: 1,
     K.item: 0,
     K.weapon: 1,
     K.food: 0,
     K.alignment: '+'},
]
"""

room_start = 1
money_start = 1000

compass_txts = {'n': 'North', 'e': 'East', 's': 'South', 'w': 'West', 'u': 'Up', 'd': 'Down'}

@dataclass
class Room(object):
    number: int
    name: str
    desc: str
    exits: dict = field(default_factory=lambda: {})  # {n e s w rc rt}
    monster: int = 0
    item: int = 0
    weapon: int = 0
    food: int = 0
    alignment: str = "neutral"  # default unless set to another guild

    def __str__(self):
        return f'#{self.number} {self.name}\n' \
               f'{self.desc}\n{self.exits}'

    def exitsTxt(self, debug: bool):
        """
        Display exits in a comma-delimited list.
        :param debug: display room #s if True
        :return: joined list of exits
        """
        # connection/transport names, index by (connection, transport)
        # rc = 1: Up     rt != 0: Room #
        # rc = 2: Down   rt == 0: Shoppe
        extra_txts = {(1, 0): 'Up to Shoppe',
                      (2, 0): 'Down to Shoppe'}
        exit_txts = []
        for k in self.exits.keys():
            if k in compass_txts:
                exit_txts.append(compass_txts[k])
        room_connection = self.exits.get('rc', 0)
        room_transport = self.exits.get('rt', 0)
        exit_extra = extra_txts.get((room_connection, room_transport))
        if exit_extra:  # is not None:
            exit_txts.append(exit_extra)
        # example: level 1, room 20
        if room_connection == 1 and room_transport != 0:
            exit_txts.append(f"Up to #{room_transport}" if debug else "Up")
        if room_connection == 2 and room_transport != 0:
            exit_txts.append(f"Down to #{room_transport}" if debug else "Down")
        return ", ".join(exit_txts)


class Item(object):
    def __init__(self, number, name, type, price, **flags):
        if flags:
            for key, value in flags.items():
                logging.info(f'{key=} {value=}')
        self.number = number
        self.name = name
        self.type = type
        self.price = price
        # this field may or may not be present:
        if flags is not None:
            self.flags = flags

    @staticmethod
    def read_items(filename: str):
        with open(filename) as jsonF:
            temp = json.load(jsonF)
            items = temp["items"]  # remove the dict "items"
        logging.info("*** Read item JSON data")

        """
        count = 0
        # 'item' becomes a copy of each dict element on each iteration of the loop:
        for item in items:
            print(f'{count:3} {item["name"]}')  # this works
            count += 1
        _ = input("Pause: ")
        print(f'{items[61]["name"]}')  # Adventurer's Guide

        count = 0
        for item in item_list:
            count += 1
            logging.info(f'{count} {item}')

            number = item['number']
            name = item['name']
            type = item['type']
            price = item['price']
            try:
                flags = item['flags']
            except KeyError:
                flags = None
            logging.info(f'{count=} {name=} {type=} {price=} {flags=}')
            temp = Item(number, name, type, price, **flags)
            logging.info(f'After Item instantiated: {temp=}')
            item_list.append(temp)
        """
        return items


class Map(object):
    def __init__(self):
        """
        Define the level map layout
        """
        self.rooms = {}

    def read_map(self, filename: str):
        """
        Data format on C64:
        * Room number        (rm)
        * Location name      (lo$)
        * items: monster, item, weapon, food
        * exits: north, east, south, west,
          RC (room command: 1=move up,
                            2=move down),
          RT (Room exit transports you to:
                 <>0: room #, or 0=Shoppe)
        https://github.com/Pinacolada64/TADA/blob/master/text/s_t_level-1-data.txt
        """

        with open(filename) as jsonF:
            map_data = json.load(jsonF)
        for room_data in map_data['rooms']:
            room = Room(**room_data)
            self.rooms[room.number] = room
            # logging.info(f'{room.number=} {room.name=}')


class Monster(object):
    def __init__(self, number, status, name, size, strength, special_weapon, to_hit, **flags):
        self.number = number
        self.status = status
        self.name = name
        # this field is optional:
        if size is not None:
            self.size = size
        self.strength = strength
        # this field is optional:
        if special_weapon is not None:
            self.special_weapon = special_weapon
        self.to_hit = to_hit
        # this field is optional:
        if flags is not None:
            self.flags = flags

    @staticmethod
    def read_monsters(filename: str):
        with open(filename) as jsonF:
            monsters = json.load(jsonF)
            # items = temp["items"]  # remove the dict "items"
        logging.info("*** Read monster JSON data")

        # count = 0
        # 'item' becomes a copy of each dict element on each iteration of the loop:
        # for item in items:
        #     print(f'{count:3} {item["name"]}')  # this works
        #     count += 1
        # _ = input("Pause: ")
        # print(f'{items[61]["name"]}')  # Adventurer's Guide

        return monsters


class Weapons(object):
    def __init__(self, number, location, name, kind, sound_effect, stability, to_hit, price, weapon_class, **flags):
        self.number = number
        self.location = location
        self.name = name
        # this field is optional:
        self.kind = kind
        self.sound_effect = sound_effect
        self.stability = stability
        self.to_hit = to_hit
        self.price = price
        self.weapon_class = weapon_class
        # this field is optional:
        if flags is not None:
            self.flags = flags

    @staticmethod
    def read_weapons(filename: str):
        with open(filename) as jsonF:
            weapons = json.load(jsonF)
        logging.info("*** Read weapon JSON data")
        return weapons


@dataclass
class Rations(object):
    number: int
    name: str
    kind: str  # magical, standard, cursed
    price: int
    flags: list

    def __init__(self, number, name, kind, price, **flags):
        self.number = number
        self.name = name
        self.kind = kind
        self.price = price
        # this field is optional:
        if flags is not None:
            self.flags = flags

    @staticmethod
    def read_rations(filename: str):
        with open(filename) as jsonF:
            rations = json.load(jsonF)
        logging.info("*** Read ration JSON data")
        return rations


server_lock = threading.Lock()


def playersInRoom(room_id: int, exclude_id: str):
    """
    Return a dict of player login id's in the room

    :param room_id: room number
    :param exclude_id: player to exclude (often the player executing the command) to not be listed
    :return: dict of players
    """
    with server_lock:
        players_in_room = room_players[room_id]
    if exclude_id is not None:
        players_in_room = players_in_room.difference({exclude_id})
    logging.info(f'{players_in_room}')
    return players_in_room


players = {}


# @dataclass
class Player:
    """
    id: str  # login id
    name: str  # player's handle
    map_level: int = 1
    room: int = 1
    money: int = 1000
    health: int = 100
    xp: int = 0

    this is to create default values for missing player.flag['foo'],
    instead of hand-editing 'player-<foo>.json' or getting KeyErrors
    if dict key player.flag['foo'] is undefined in said file
    https://docs.python.org/3.8/library/dataclasses.html?highlight=dataclass#dataclasses.field
    
    this is useful also, but cannot be used in the dataclass context:
    https://docs.python.org/3/library/collections.html?highlight=default%20factory#collections.defaultdict

    # flag: dict = field(default_factory=dict)
    flag: dict = field(default_factory=lambda: {})
    # for saving previous command to repeat with Return/Enter
    # (it may be expanded to a list in the future):
    last_command: str = None
    """

    def __init__(self, id, name, map_level, room, money, health, xp,
                 flag, last_command):
        logging.info(f"Instantiating player '{name}'.")
        self.id: str = id  # login id
        self.name: str = name  # player's handle
        self.map_level: int = map_level  # to differentiate between eXPerience level
        self.room: int = room  # default: room_start = 1
        self.money: int = money  # default: money_start = 1000
        self.health: int = health  # default 100
        self.xp: int = xp
        self.flag = dict(flag)
        self.last_command: str = last_command

    def connect(self):
        with server_lock:
            room_players[self.room].add(self.id)
            # TODO: notify other players of connection

    def move(self, next_room: int, direction=None):
        """
        remove player login id from list of players in current_room, add them to room next_room
        :param next_room: room to move to
        :param direction: direction being moved in, for notifying other players of movement
        if None, '#<room_number>' teleportation command (or, later, spell) was used and the
        "<player> disappears in a flash of light" message is used instead
        """
        current_room = self.room
        with server_lock:
            logging.debug(f"Before remove: {room_players=}")
            room_players[current_room].remove(self.id)
            logging.debug(f"After remove: {room_players=}")

            self.room = next_room
            logging.debug(f"Before add: {room_players=}")
            room_players[self.room].add(self.id)
            logging.debug(f"After add: {room_players=}")
            logging.info(f'Moved {self.name} from {current_room} to {self.room}')
            # teleport command doesn't require direction, just room #
            if direction is None:
                return Message(lines=[f'[{self.name} disappears in a flash of light.'])
            else:
                return Message(lines=[f"{self.name} moves {compass_txts[direction]}."])

    def disconnect(self):
        with server_lock:
            room_players[self.room].remove(self.id)
            return Message(lines=[f'{players[self.id].name} falls asleep.'])
        # FIXME: is this orphaned code?
        #  print(f"You are in {self.room}.\n{playersInRoom(self.room)} is here.")

    @staticmethod
    def _json_path(user_id):
        return os.path.join(net_common.run_server_dir, f"player-{user_id}.json")

    @staticmethod
    def load(user_id):
        path = Player._json_path(user_id)
        if os.path.exists(path):
            with open(path) as jsonF:
                lh_data = json.load(jsonF)
            return Player(**lh_data)
        else:
            return None

    def save(self):
        with open(Player._json_path(self.id), 'w') as jsonF:
            json.dump(self, jsonF, default=lambda o: {k: v for k, v
                                                      # in o.__dict__.items() if v}, indent=4)
                                                      in o.__dict__.items()}, indent=4)
        return Message(lines=[f'Saved {self.name}.'])


class PlayerHandler(net_server.UserHandler):
    def initSuccessLines(self):
        return ['Welcome to:\n', 'Totally\nAwesome\nDungeon\nAdventure\n', 'Please log in.']

    def loginFailLines(self):
        return ['Please try again.']

    def roomMsg(self, lines: list, changes: dict):
        """
        Display the room description and contents to the player in the room

        :param lines: text to output. each line is an element of a list.
        :param changes: ...?
        :return: Message object
        """
        # get room # that player is in
        try:
            room = game_map.rooms[self.player.room]
        except KeyError:
            logging.warning(f"Room #{room.number} does not exist")

        debug = self.player.flag['debug']
        exitsTxt = room.exitsTxt(debug)
        lines2 = list(lines)

        # display room header
        # check for/trim room flags (currently only '->'):
        temp = room.name.rfind("|")
        room_name = room.name
        room_flags = ''
        if temp != -1:
            room_name = room.name[:temp]
            room_flags = room.name[temp + 1:]

        temp = str(room.alignment).title()
        lines2.append(f"{f'#{room.number} ' if debug else ''}{room_name} [{temp}]\n")

        # FIXME: is anything wrong with this?
        if self.player.flag['room_descs']:
            lines2.append(f'{wrapper.fill(text=room.desc)}')

        # is an item in current room?
        # logging.info(f'{room=}')  # raw info
        obj_list = []  # TODO: for grammatical list and .join(",") later
        item = room.item
        if item:
            obj_name = items[item - 1]["name"]
            obj_list.append(obj_name)
            lines2.append(f'You see item #{item} {obj_name}')

        food = room.food
        if food:
            food_name = rations[room.food - 1]["name"]
            # TODO: obj_list.append(food_name)
            lines2.append(f'You see food #{food} {food_name}')

        monster = room.monster
        if monster:
            m = monsters[monster - 1]
            mon_name = m["name"]
            # optional info:
            try:
                mon_size = m["size"]
            except KeyError:
                mon_size = None
            # TODO: obj_list.append(mon_name)
            lines2.append(f"You see monster #{monster}: "
                          f"{f'{mon_size} ' if mon_size is not None else ''}"
                          f"{mon_name}")

        weapon = room.weapon  # weapon number
        if weapon:
            w = weapons[weapon - 1]
            weapon_name = w["name"]
            # TODO: obj_list.append(weapon_name)
            lines2.append(f'You see weapon #{weapon} {weapon_name}')

        # TODO: add grammatical list item (SOME MELONS, AN ORANGE)

        debug = self.player.flag['debug']
        exits_txt = room.exitsTxt(debug)
        if exits_txt is not None:
            lines2.append(f"Ye may travel: {exitsTxt}\n")
            # ryan: list exit dirs and room #s
            if debug:
                for k, v in room.exits.items():
                    logging.info(f"Exit '{k}' to {v}")

        # show item in room:
        # num = 62  # zero-based numbering, so subtract one to get actual object
        # logging.info(f'item #{num} name: {items[num - 1]["name"]}')

        # setting 'exclude_id' excludes that player (i.e., yourself) from being listed
        other_player_ids = playersInRoom(room.number, exclude_id=self.player.id)
        # TODO: "Alice is here." / "Alice and Bob are here." / "Alice, Bob and Mr. X are here."
        """
        if len(other_player_ids) == 0:
            logging.info("No other players here.")
        if len(other_player_ids) > 0:
            result_list = []
            result_list.append(i for i in other_player_ids)
            if len(result_list) == 1:
                result_list = f"{result_list} is"
            if len(result_list) > 1:
                # tanabi: Add 'and' if we need it
                # result_list = f"and {result_list[:-1]} are"
                pass
        other_player_ids = playersInRoom(room.id, self.player.id)
        lines2.append(f"{result_list} here.")
        """

        if len(other_player_ids) > 0:
            other_players = ', '.join([players[id].name for id in other_player_ids])
            temp = 'is' if len(other_players) == 1 else 'are'
            lines2.append(f"{other_players} {temp} here.")
        return Message(lines=lines2, changes=changes)

    def processLoginSuccess(self, user_id):
        player = Player.load(user_id)
        if player is None:
            # TODO: create player
            valid_name = False
            while not valid_name:
                reply = self.promptRequest(lines=["Choose your adventurer's name."], prompt='Name? ')
                name = reply['text'].strip()
                if name != '':  # TODO: limitations on valid names
                    valid_name = True
            player = Player(id=user_id,
                            name=name,
                            map_level=1,
                            room=room_start,
                            money=money_start,
                            health=100,
                            xp=0,
                            flag={'debug': True,
                                  'expert_mode': False,
                                  'room_descs': True},
                            last_command=None)
            player.save()
        self.player = players[user_id] = player
        logging.info(f"login {user_id} '{self.player.name}' (addr={self.sender})")
        money = self.player.money
        lines = [f"Welcome, {self.player.name}.", f"You have {money:,} gold.\n"]

        # show/convert flags from json text 'true/false' to bool True/False
        # (otherwise they're not recognized, and can't be toggled):
        for k, v in self.player.flag.items():
            if self.player.flag[k] == 'true':
                self.player.flag[k] = True
            if self.player.flag[k] == 'false':
                self.player.flag[k] = False
            logging.info(f'{k=} {v=}')

        # FIXME
        changes = {K.room_name: game_map.rooms[self.player.room].name,
                   K.money: self.player.money, K.health: self.player.health,
                   K.xp: self.player.xp}
        self.player.connect()
        return self.roomMsg(lines, changes)

    def processMessage(self, data):
        logging.info('processMessage()')
        if 'text' in data:
            cmd = data['text'].lower().split(' ')
            logging.info(f"{self.player.id}: {cmd}")
            # update last command to repeat with Return/Enter
            # if an invalid command, set to None later
            # TODO: maybe maintain a history
            self.player.last_command = cmd
            logging.info(f'{self.player.last_command=}')

            # TODO: handle commands with parser etc.

            # movement
            if cmd[0] in compass_txts:
                room = game_map.rooms[self.player.room]
                logging.info(f'current room #: {self.player.room}')
                direction = cmd[0]
                logging.info(f"direction: {direction}")
                # 'rooms' is a list of Room objects?
                logging.info(f'exits: {room.exits}')
                # >>> exits = {'n': 1, 's': 3}
                # >>> exits.keys()
                # dict_keys(['n', 's'])
                # >>> exits['n']
                # 1
                # cmd.insert(0, 'go') probably not necessary
                # json data (dict):
                # check if 'direction' is in room exits
                if direction in room.exits:  # rooms[self.player.room].exits.keys():
                    logging.info(f"{direction=} => {self.player.room=}")
                    # delete player from list of players in current room,
                    # add player to list of players in room they moved to
                    self.player.move(room.exits[direction], direction)
                    # FIXME: maybe only at quit
                    # self.player.save()
                    room_name = game_map.rooms[self.player.room].name
                    return self.roomMsg(lines=[f"You move {compass_txts[direction]}."],
                                        changes={K.room_name: room_name})

            """
            This is the way the original Apple code handled up/down exits.
            I'm fully aware up/down exits could just be a room number, or 0
            for no connection--my self-written level 8 map does exactly this.
            """
            if cmd[0][:1] == 'u' or cmd[0][:1] == 'd':
                room = game_map.rooms[self.player.room]
                room_exits = room.exits
                room_connection = room_exits.get('rc', 0)
                room_transport = room_exits.get('rt', 0)
                # example: level 1, room 20
                if cmd[0] == 'u' and room_connection == 1:
                    if room_transport != 0:
                        logging.info(f'{self.player.name} moves Up to #{room_transport}')
                        # self.player.room = room_transport
                        self.player.move(next_room=room_transport, direction='u')
                        return
                    else:
                        logging.info(f'{self.player.name} moves Up to Shoppe')
                        self.player.move(next_room=room_transport, direction='u')
                        # don't change self.player.room, return them to where they left
                        return Message(lines=["TODO: write Shoppe routine..."])
                if cmd[0] == 'd' and room_connection == 2:
                    if room_transport != 0:
                        logging.info(f'{self.player.name} moves Down to #{room_transport}')
                        self.player.move(next_room=room_transport, direction='d')

                        # get new room desc:
                        # FIXME: TypeError: 'Room' object is not subscriptable
                        """
                        temp = game_map.rooms[number]
                        logging.info(f"room info: {temp}")
                        desc = temp["desc"]
                        logging.info(f"desc: {desc}")
                        """
                        desc = "bla"
                        # FIXME: see server.py, line 24:
                        #  thought maybe this would show the new room desc
                        return Message(lines=["You move down."],
                                       changes={K.desc: desc})
                    else:
                        logging.info(f'{self.player.name} moves Down to Shoppe')
                        self.player.move(next_room=room_transport, direction='d')

                        # don't change self.player.room, return them to where they left
                        return Message(lines=["TODO: write Shoppe routine..."])

                else:
                    return Message(lines=["Ye cannot travel that way."])

            if cmd[0] in ['l', 'look']:
                return self.roomMsg(lines=[], changes={})

            if cmd[0] in ['bye', 'logout', 'quit']:
                temp = net_server.UserHandler.promptRequest(self, lines=[], prompt='Really quit? ',
                                                            choices={'y': 'yes', 'n': 'no'})
                # returns a Cmd object?
                logging.info(f'{temp=}')
                # extract value from returned dict, e.g.: temp={'text': 'y'}
                if temp.get('text') == 'y':
                    self.player.save()
                    self.player.disconnect()
                    return Message(lines=["Bye for now."], mode=Mode.bye)
                else:
                    return Message(lines=["Thanks for sticking around."])

            if cmd[0] in ['?', 'hel', 'help']:
                from tada_utilities import game_help
                game_help(self, cmd)
                return Message(lines=["Done."])

            if cmd[0] in ['cheatcode']:
                return Message(lines=["↑ ↑ ↓ ↓ ← → ← → B A"])

            # toggle room descriptions:
            if cmd[0] in ['r']:
                logging.info(f"{self.player.flag['room_descs']}")
                self.player.flag['room_descs'] = not self.player.flag['room_descs']
                temp = self.player.flag['room_descs']
                logging.info(f'Room descriptions: {temp}.')
                return Message(lines=[f'[Room descriptions are now '
                                      f'{"off" if temp is False else "on"}.]'])

            if cmd[0] == 'who':
                from server import net_server as ns
                lines = ["\nWho's on:"]
                count = 0
                for login_id in ns.connected_users:
                    lines.append(f'{count + 1:2}) {players[login_id].name}')
                    count += 1
                return Message(lines=lines)

            # really this is just a debugging tool to save shoe leather:
            if cmd[0][:1] == "#":
                temp = cmd[0][1:]
                if temp.isdigit() is False:
                    return Message(lines=["(Room number required after '#'.)"])
                val = int(temp)
                try:
                    # get destination room data:
                    dest = game_map.rooms[val]
                    room_num = dest.number
                    # delete player id from list of players in current room,
                    # add player id to list of players in room they moved to
                    # 'direction' is None, so display "{player} disappears in a flash of light."
                    self.player.move(room_num, direction=None)

                    # move player there:
                    self.player.room = room_num
                    logging.info(f'{room_num=} {self.player.room=}')
                    # TODO: something like this displayed to other players would be nice to indicate teleportation:
                    #  Message([f"{self.player.name} disappears in a flash of light.")
                    # TODO: display new room description
                    return Message(lines=[f"You teleport to room #{val}, {dest.name}.\n"])
                    # changes={"prompt": "Prompt:", "status_line": 'Status Line'})
                except KeyError:
                    return Message(lines=[f'Teleport: No such room yet (#{val}, '
                                   f'max of {max(game_map.rooms)}).'])

            """
            FIXME: Under consideration, but not sure how to set this up
            if cmd[0] == 'petscii':
                header = 'PetSCII Strings:'
                midline = b'\xc0' * len(header)  # solid '-'
                lines = [f'{header}', f'{midline}',
                         'HELLO 123 @!\x5c = HELLO 123 @!£',
                         '\x12 \uf11a',  # reverse video
                         '\xd3 ♥',
                         '\xff π',
                         '✓'
                         ]
                for line in lines:
                    # must ignore \x0a (linefeed), gives MappingError
                    temp = line + '\n'
                    # data = temp.encode(encoding='petscii-c64en-lc', errors='ignore')
                    data = temp.encode(encoding='utf-8', errors='ignore')
                    logging.info(f'data={type(data)}')  # type = bytes
                    data_dict = dict(data)
                    net_server.UserHandler.message(net_common.toJSONB(data_dict))
                    net_server.UserHandler.message(self, "This should be PetSCII.\r")  # socket: request.sendall(data)
            """
            # invalidate repeating last_command
            self.player.last_command = None
            return Message(lines=["I didn't understand that.  Try something else."])
        else:
            logging.error("unexpected message")
            return Message(lines=["Unexpected message."], mode=Mode.bye)


def break_handler(signal_received):
    # Handle any cleanup here
    t = signal.Signals  # to display signal name
    logging.warning(f'{signal_received} SIGINT or Ctrl-C detected. Shutting down server.')
    # TODO: broadcast shutdown message to all players
    print("Server going down. Bye.")
    exit(0)


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.DEBUG, format='[%(levelname)s] | %(message)s')

    import signal
    # exit gracefully when SIGINT is received
    # signal(SIGINT, handler)  # for *nix
    signal.signal(signal.SIGINT, break_handler)  # for Windows

    wrapper = textwrap.TextWrapper(width=80)

    # load game data
    # load map
    game_map = Map()
    game_map.read_map("level_1.json")

    # rooms = {}
    # for data in game_map.rooms:
    #     print(type(data.number))
    #     n = int(data.number)
    #     room = Room(number=n, name=data.name, desc=data.desc, exits=data.exits,
    #                 monster=data.monster, item=data.item, weapon=data.weapon, food=data.food,
    #                 alignment=data.alignment)
    #     rooms[data.number] = room
    # FIXME: determine how this works, it just copies 'set()' for each item in the list:
    room_players = {number: set() for number in game_map.rooms.keys()}
    logging.info(f'{room_players=}')

    # load items
    items = Item.read_items("objects.json")

    # load monsters
    monsters = Monster.read_monsters("monsters.json")

    # load weapons
    weapons = Weapons.read_weapons("weapons.json")

    # load rations
    rations = Rations.read_rations("rations.json")

    host = "localhost"
    net_server.start(host, common.server_port, common.app_id, common.app_key,
                     common.app_protocol, PlayerHandler)
