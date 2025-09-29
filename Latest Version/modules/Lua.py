#coding: utf-8
import time, json, re, asyncio, math, random, threading
from lupa import LuaRuntime
from utils import Utils
from ByteArray import ByteArray
from Identifiers import Identifiers

class StoppableThread(threading.Thread):
    """Thread class with a stop() method. The thread itself has to check
    regularly for the stopped() condition."""

    def __init__(self,  *args, **kwargs):
        super(StoppableThread, self).__init__(*args, **kwargs)
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def stopped(self):
        return self._stop_event.is_set()
        
class Lua:
    def __init__(self, room, server):
        # Others
        self.room = room
        self.server = server
        # NoneType
        self.owner = None
        self.runtime = None
        self._G = None
        self._globals = None
        # String
        self.name = ""
        self.script = ""
        self.customxml = ""
        # Boolean
        self.running = True
        # Dict
        self.RoomObjects = {}
        self.loops = {}
        #List
        self.HiddenCommands = []
        self.imagesadd = []
        self.functions = []
        # Integer
        self.LastRoomObjectID = 2000
        self.lastloopid = 1
        self.maxData = 128000
    
    def FixUnicodeError(self, text=u""):
        if isinstance(text, bytes):
            text = text.decode()
        return text

    def CheckPerms(self, function):
        if self.owner == None or (self.owner.isLuaCrew or self.owner.privLevel in [9, 3]):
            return True
        self.owner.playerException.Invoke("notallowedlua", self.owner.playerName, function)
        return False
    
    def htmlfix(self, text):
        if "<a" in text:
            if not "</a>" in text:
                text = text + "</a>"
        if "<p" in text:
            if not "</p>" in text:
                text = text + "</p>"
        if "<font" in text:
            if not "</font>" in text:
                text = text + "</font>"
        return text

    def createLoop(self, _id, _time, callback):
        if not self.running: return
        self.server.loop.call_later(0, callback)
        d = self.server.loop.call_later(_time, lambda: self.createLoop(_id, _time, callback))
        if _id in self.loops:
            self.loops[_id] = d
        else:
            return d

    def tableForeach(self, array, callback):
        for key, value in array.items():
            callback(key, value)
               
    def sendLuaMessage(self, *args): 
        message = ""
        for x in args:
            temp = (self._globals.tostring(x) if self._globals.type(x) != "userdata" else "userdata") + ("  " if len(args) > 1 else "")
            if "table" in temp:
                message += str(dict(x))
            else:
                if '.0' in temp:
                    temp = str(int(float(temp)))
                message += temp
        if message and self.owner != None:
            self.owner.sendLuaMessage(message)

    def EventLoop(self):
        if not self.runtime is None:
            self.RefreshTFMGet()
            elapsed = (Utils.getTime() - self.room.gameStartTime) * 1000
            remaining = ((self.room.roundTime + self.room.addTime) - (Utils.getTime() - self.room.gameStartTime)) * 1000
            self.emit('Loop', (elapsed if elapsed >= 0 else 0, remaining if remaining >= 0 else 0))

            self.server.loop.call_later(0.5, self.EventLoop)
    
    def UpdateLua(self, fnc2, to_update, added=''):
        if self._G is None or self._globals is None: return
        for fnc in fnc2:
            if isinstance(fnc2[fnc], dict):
                if not fnc in dict(to_update):
                    to_update[fnc] = self.runtime.eval('{}')
                add = added + fnc + '.'
                self.UpdateLua(fnc2[fnc],to_update[fnc],add)
            elif callable(fnc2[fnc]):
                if fnc in dict(to_update) and fnc in self.functions: continue
                to_update[fnc] = self.runtime.eval(f'function(...) return system.callback("{added+fnc}", ...);end')
                self.functions.append(fnc)
            else:
                to_update[fnc] = fnc2[fnc]
           

    def SetupRuntimeGlobals(self): 
        if self.runtime is None: 
            return
        if self._G is None:
            self._G = {}
            self._globals = self.runtime.globals()


        self._G['table'] = {}
        self._G['table']['foreach'] = self.tableForeach
        
        self._G['bit32'] = {}
        self._G['bit32']['band'] = lambda x,y: x & y

        self._G['os'] = {}
        #self._G['os']['exit'] = self.stopModule
        self._G['os']['getenv'] = None
        self._G['os']['remove'] = None
        self._G['os']['rename'] = None
        self._G['os']['execute'] = None
        self._G['os']['setlocale'] = None
        #self._G['os']['time'] = lambda: int(time.time() * 1000)
        self._G['math'] = {}
        self._G['math']['atan2'] = math.atan2
        self._G['math']['random'] = self.random
        self._G['print'] = self.sendLuaMessage

        self._G['system'] = {}
        self._G['system']['bindKeyboard'] = self.room.bindKeyBoard
        self._G['system']['bindMouse'] = self.room.bindMouse #self.runtime.eval('function(...) return system.callback("bindMouse", ...);end')
        self._G['system']['disableChatCommandDisplay'] = self.disableChatCommandDisplay
        self._G['system']['exit'] = self.stopModule
        #self._G['system']['callback'] = self.callback
        #self._G['system']['giveEventGift'] = self.giveEventGift
        self._G['system']['loadFile'] = self.loadFile
        self._G['system']['loadPlayerData'] = self.loadPlayerData
        self._G['system']['newTimer'] = self.newTimer
        self._G['system']['removeTimer'] = self.removeTimer
        self._G['system']['saveFile'] = self.saveFile
        self._G['system']['savePlayerData'] = self.savePlayerData
        self._G['system']['luaEventLaunchInterval'] = self.luaEventLaunchInterval
        self._G['system']['setLuaEventBanner'] = self.setLuaEventBanner
        self._G['system']['giveAdventurePoint'] = self.giveAdventurePoint

        self._G['ui'] = {}
        self._G['ui']['addLog'] = self.addLog
        self._G['ui']['addPopup'] = self.room.addPopup
        self._G['ui']['addTextArea'] = self.room.addTextArea
        self._G['ui']['setBackgroundColor'] = self.setBackgroundColor
        self._G['ui']['removeTextArea'] = self.room.removeTextArea
        self._G['ui']['setMapName'] = self.setMapName
        self._G['ui']['setShamanName'] = self.setShamanName
        self._G['ui']['showColorPicker'] = self.room.showColorPicker
        self._G['ui']['updateTextArea'] = self.room.updateTextArea

        self._G['tfm'] = {}
        self._G['tfm']['enum'] = {}
        self._G['tfm']['enum']['shamanObject'] = {}
        self._G['tfm']['enum']['emote'] = {}
        self._G['tfm']['enum']['bonus'] = {}
        self._G['tfm']['enum']['ground'] = {}
        self._G['tfm']['enum']['particle'] = {}
        self._G['tfm']['exec'] = {}
        self._G['tfm']['get'] = {}
        self._G['tfm']['get']['misc'] = {}
        self._G['tfm']['get']['room'] = {}
        
        self._G['tfm']['exec']['addBonus'] = self.addBonus
        self._G['tfm']['exec']['addConjuration'] = self.addConjuration
        self._G['tfm']['exec']['addImage'] = self.addImage
        self._G['tfm']['exec']['addJoint'] = self.addJoint
        self._G['tfm']['exec']['addNPC'] = self.room.spawnNPC
        self._G['tfm']['exec']['addPhysicObject'] = self.room.addPhysicObject
        self._G['tfm']['exec']['addShamanObject'] = self.addShamanObject
        self._G['tfm']['exec']['attachBalloon'] = self.attachBalloon
        self._G['tfm']['exec']['bindKeyboard'] = self.room.bindKeyBoard
        self._G['tfm']['exec']['changePlayerSize'] = self.changePlayerSize
        self._G['tfm']['exec']['chatMessage'] = self.chatMessage
        self._G['tfm']['exec']['disableAfkDeath'] = self.disableAfkDeath
        self._G['tfm']['exec']['disableAllShamanSkills'] = self.disableAllShamanSkills
        self._G['tfm']['exec']['disableAutoNewGame'] = self.disableAutoNewGame
        self._G['tfm']['exec']['disableAutoScore'] = self.disableAutoScore
        self._G['tfm']['exec']['disableAutoShaman'] = self.disableAutoShaman
        self._G['tfm']['exec']['disableAutoTimeLeft'] = self.disableAutoTimeLeft
        self._G['tfm']['exec']['disableDebugCommand'] = self.disableDebugCommand
        self._G['tfm']['exec']['disableMinimalistMode'] = self.disableMinimalistMode
        self._G['tfm']['exec']['disableMortCommand'] = self.disableMortCommand
        self._G['tfm']['exec']['disableWatchCommand'] = self.disableWatchCommand
        self._G['tfm']['exec']['disablePhysicalConsumables'] = self.disablePhysicalConsumables
        self._G['tfm']['exec']['displayParticle'] = self.displayParticle
        self._G['tfm']['exec']['explosion'] = self.explosion
        self._G['tfm']['exec']['freezePlayer'] = self.freezePlayer
        self._G['tfm']['exec']['getPlayerSync'] = self.getPlayerSync
        self._G['tfm']['exec']['giveCheese'] = self.giveCheese
        self._G['tfm']['exec']['giveConsumables'] = self.giveConsumables
        self._G['tfm']['exec']['giveMeep'] = self.giveMeep
        self._G['tfm']['exec']['giveTransformations'] = self.giveTransformations
        self._G['tfm']['exec']['killPlayer'] = self.killPlayer
        self._G['tfm']['exec']['linkMice'] = self.linkMice
        self._G['tfm']['exec']['stopMusic'] = self.stopMusic
        self._G['tfm']['exec']['lowerSyncDelay'] = self.lowerSyncDelay
        self._G['tfm']['exec']['moveCheese'] = self.moveCheese
        self._G['tfm']['exec']['moveObject'] = self.moveObject
        self._G['tfm']['exec']['movePhysicObject'] = self.moveObject
        self._G['tfm']['exec']['movePlayer'] = self.room.movePlayer
        self._G['tfm']['exec']['newGame'] = self.newGame
        self._G['tfm']['exec']['playEmote'] = self.playEmote
        self._G['tfm']['exec']['playSound'] = self.playSound
        self._G['tfm']['exec']['playerVictory'] = self.playerVictory
        self._G['tfm']['exec']['removeBonus'] = self.removeBonus
        self._G['tfm']['exec']['removeCheese'] = self.removeCheese
        self._G['tfm']['exec']['removeImage'] = self.removeImage
        self._G['tfm']['exec']['removeJoint'] = self.removeJoint
        self._G['tfm']['exec']['removeObject'] = self.room.removeObject
        self._G['tfm']['exec']['removePhysicObject'] = self.RemovePhysicObject
        self._G['tfm']['exec']['respawnPlayer'] = self.respawnPlayer
        self._G['tfm']['exec']['setAieMode'] = self.setAieMode
        self._G['tfm']['exec']['setAutoMapFlipMode'] = self.setAutoMapFlipMode
        self._G['tfm']['exec']['setGameTime'] = self.setGameTime
        self._G['tfm']['exec']['setPlayerGravityScale'] = self.setPlayerGravityScale
        self._G['tfm']['exec']['setPlayerNightMode'] = self.setPlayerNightMode
        self._G['tfm']['exec']['setNameColor'] = self.room.setNameColor
        self._G['tfm']['exec']['setPlayerScore'] = self.setPlayerScore
        self._G['tfm']['exec']['setPlayerSync'] = self.setPlayerSync
        self._G['tfm']['exec']['setRoomMaxPlayers'] = self.setRoomMaxPlayers
        self._G['tfm']['exec']['setRoomPassword'] = self.setRoomPassword
        self._G['tfm']['exec']['setShaman'] = self.setShaman
        self._G['tfm']['exec']['setUIMapName'] = self.setMapName
        self._G['tfm']['exec']['setUIShamanName'] = self.setShamanName
        self._G['tfm']['exec']['setVampirePlayer'] = self.setVampirePlayer
        self._G['tfm']['exec']['setWorldGravity'] = self.setWorldGravity
        #self._G['tfm']['exec']['stopSound'] = self.stopSound
        
        self._G['tfm']['exec']['snow'] = self.snow
        self._G['tfm']['get']['misc']['apiVersion'] = "0.28"
        self._G['tfm']['get']['misc']['transformiceVersion'] = self.server.Version

        self._G['tfm']['get']['room']['objectList'] = {}
        self._G['tfm']['get']['room']['xmlMapInfo'] = {}
        
        #self._G['debug']['disableEventLog'] = self.disableEventLog
        self._globals['system'] = self.runtime.eval('{}')
        self._globals['system']['callback'] = self.callback
        self.RefreshTFMGet()

    def RefreshTFMGet(self):
        self._G['tfm']['get']['room']['xmlMapInfo']['permCode'] = self.room.mapPerma
        self._G['tfm']['get']['room']['xmlMapInfo']['author'] = self.room.mapName
        self._G['tfm']['get']['room']['xmlMapInfo']['mapCode'] = self.room.mapCode
        self._G['tfm']['get']['room']['xmlMapInfo']['xml'] = self.room.mapXML
        
        self._G['tfm']['enum']['shamanObject']['arrow'] = 0
        self._G['tfm']['enum']['shamanObject']['littleBox'] = 1
        self._G['tfm']['enum']['shamanObject']['box'] = 2
        self._G['tfm']['enum']['shamanObject']['littleBoard'] = 3
        self._G['tfm']['enum']['shamanObject']['board'] = 4
        self._G['tfm']['enum']['shamanObject']['ball'] = 6
        self._G['tfm']['enum']['shamanObject']['trampoline'] = 7
        self._G['tfm']['enum']['shamanObject']['anvil'] = 10
        self._G['tfm']['enum']['shamanObject']['cannon'] = 19
        self._G['tfm']['enum']['shamanObject']['bomb'] = 23
        self._G['tfm']['enum']['shamanObject']['orangePortal'] = 26
        self._G['tfm']['enum']['shamanObject']['blueBalloon'] = 28
        self._G['tfm']['enum']['shamanObject']['redBalloon'] = 29
        self._G['tfm']['enum']['shamanObject']['greenBalloon'] = 30
        self._G['tfm']['enum']['shamanObject']['yellowBalloon'] = 31
        self._G['tfm']['enum']['shamanObject']['rune'] = 32
        self._G['tfm']['enum']['shamanObject']['chicken'] = 33
        self._G['tfm']['enum']['shamanObject']['snowBall'] = 34
        self._G['tfm']['enum']['shamanObject']['cupidonArrow'] = 35
        self._G['tfm']['enum']['shamanObject']['apple'] = 39
        self._G['tfm']['enum']['shamanObject']['sheep'] = 40
        self._G['tfm']['enum']['shamanObject']['littleBoardIce'] = 45
        self._G['tfm']['enum']['shamanObject']['littleBoardChocolate'] = 46
        self._G['tfm']['enum']['shamanObject']['iceCube'] = 54
        self._G['tfm']['enum']['shamanObject']['cloud'] = 57
        self._G['tfm']['enum']['shamanObject']['bubble'] = 59
        self._G['tfm']['enum']['shamanObject']['tinyBoard'] = 60
        self._G['tfm']['enum']['shamanObject']['companionCube'] = 61
        self._G['tfm']['enum']['shamanObject']['stableRune'] = 62
        self._G['tfm']['enum']['shamanObject']['ballonFish'] = 65
        self._G['tfm']['enum']['shamanObject']['longBoard'] = 67
        self._G['tfm']['enum']['shamanObject']['triangle'] = 68
        self._G['tfm']['enum']['shamanObject']['sBoard'] = 69
        self._G['tfm']['enum']['shamanObject']['paperPlane'] = 80
        self._G['tfm']['enum']['shamanObject']['rock'] = 85
        self._G['tfm']['enum']['shamanObject']['pumpkinBall'] = 89
        self._G['tfm']['enum']['shamanObject']['tombstone'] = 90
        self._G['tfm']['enum']['shamanObject']['paperBall'] = 95
        
        self._G['tfm']['enum']['emote']['dance'] = 0
        self._G['tfm']['enum']['emote']['laugh'] = 1
        self._G['tfm']['enum']['emote']['cry'] = 2
        self._G['tfm']['enum']['emote']['kiss'] = 3
        self._G['tfm']['enum']['emote']['angry'] = 4
        self._G['tfm']['enum']['emote']['clap'] = 5
        self._G['tfm']['enum']['emote']['sleep'] = 6
        self._G['tfm']['enum']['emote']['facepaw'] = 7
        self._G['tfm']['enum']['emote']['sit'] = 8
        self._G['tfm']['enum']['emote']['confetti'] = 9
        self._G['tfm']['enum']['emote']['flag'] = 10
        self._G['tfm']['enum']['emote']['marshmallow'] = 11
        self._G['tfm']['enum']['emote']['selfie'] = 12
        self._G['tfm']['enum']['emote']['highfive'] = 13
        self._G['tfm']['enum']['emote']['highfive_1'] = 14
        self._G['tfm']['enum']['emote']['highfive_2'] = 15
        self._G['tfm']['enum']['emote']['partyhorn'] = 16
        self._G['tfm']['enum']['emote']['hug'] = 17
        self._G['tfm']['enum']['emote']['hug_1'] = 18
        self._G['tfm']['enum']['emote']['hug_2'] = 19
        self._G['tfm']['enum']['emote']['jigglypuff'] = 20
        self._G['tfm']['enum']['emote']['kissing'] = 21
        self._G['tfm']['enum']['emote']['kissing_1'] = 22
        self._G['tfm']['enum']['emote']['kissing_2'] = 23
        self._G['tfm']['enum']['emote']['carnaval'] = 24
        self._G['tfm']['enum']['emote']['rockpaperscissors'] = 25
        self._G['tfm']['enum']['emote']['rockpaperscissors_1'] = 26
        self._G['tfm']['enum']['emote']['rockpaperscissor_2'] = 27
        
        self._G['tfm']['enum']['bonus']['point'] = 0
        self._G['tfm']['enum']['bonus']['speed'] = 1
        self._G['tfm']['enum']['bonus']['death'] = 2
        self._G['tfm']['enum']['bonus']['spring'] = 3
        self._G['tfm']['enum']['bonus']['booster'] = 5
        self._G['tfm']['enum']['bonus']['electricArc'] = 6
        
        self._G['tfm']['enum']['ground']['wood'] = 0
        self._G['tfm']['enum']['ground']['ice'] = 1
        self._G['tfm']['enum']['ground']['trampoline'] = 2
        self._G['tfm']['enum']['ground']['lava'] = 3
        self._G['tfm']['enum']['ground']['chocolate'] = 4
        self._G['tfm']['enum']['ground']['earth'] = 5
        self._G['tfm']['enum']['ground']['grass'] = 6
        self._G['tfm']['enum']['ground']['sand'] = 7
        self._G['tfm']['enum']['ground']['cloud'] = 8
        self._G['tfm']['enum']['ground']['water'] = 9
        self._G['tfm']['enum']['ground']['stone'] = 10
        self._G['tfm']['enum']['ground']['snow'] = 11
        self._G['tfm']['enum']['ground']['rectangle'] = 12
        self._G['tfm']['enum']['ground']['circle'] = 13
        self._G['tfm']['enum']['ground']['invisible'] = 14
        self._G['tfm']['enum']['ground']['web'] = 15
        self._G['tfm']['enum']['ground']['yellowGrass'] = 17
        self._G['tfm']['enum']['ground']['pinkGrass'] = 18
        self._G['tfm']['enum']['ground']['acid'] = 19
        
        self._G['tfm']['enum']['particle']['whiteGlitter'] = 0
        self._G['tfm']['enum']['particle']['blueGlitter'] = 1
        self._G['tfm']['enum']['particle']['orangeGlitter'] = 2
        self._G['tfm']['enum']['particle']['cloud'] = 3
        self._G['tfm']['enum']['particle']['dullWhiteGlitter'] = 4
        self._G['tfm']['enum']['particle']['heart'] = 5
        self._G['tfm']['enum']['particle']['bubble'] = 6
        self._G['tfm']['enum']['particle']['tealGlitter'] = 9
        self._G['tfm']['enum']['particle']['spirit'] = 10
        self._G['tfm']['enum']['particle']['yellowGlitter'] = 11
        self._G['tfm']['enum']['particle']['ghostSpirit'] = 12
        self._G['tfm']['enum']['particle']['redGlitter'] = 13
        self._G['tfm']['enum']['particle']['waterBubble'] = 14
        self._G['tfm']['enum']['particle']['plus1'] = 15
        self._G['tfm']['enum']['particle']['plus10'] = 16
        self._G['tfm']['enum']['particle']['plus12'] = 17
        self._G['tfm']['enum']['particle']['plus14'] = 18
        self._G['tfm']['enum']['particle']['plus16'] = 19
        self._G['tfm']['enum']['particle']['meep'] = 20
        self._G['tfm']['enum']['particle']['redConfetti'] = 21
        self._G['tfm']['enum']['particle']['greenConfetti'] = 22
        self._G['tfm']['enum']['particle']['blueConfetti'] = 23
        self._G['tfm']['enum']['particle']['yellowConfetti'] = 24
        self._G['tfm']['enum']['particle']['diagonalRain'] = 25
        self._G['tfm']['enum']['particle']['curlyWind'] = 26
        self._G['tfm']['enum']['particle']['wind'] = 27
        self._G['tfm']['enum']['particle']['rain'] = 28
        self._G['tfm']['enum']['particle']['star'] = 29
        self._G['tfm']['enum']['particle']['littleRedHeart'] = 30
        self._G['tfm']['enum']['particle']['littlePinkHeart'] = 31
        self._G['tfm']['enum']['particle']['daisy'] = 32
        self._G['tfm']['enum']['particle']['bell'] = 33
        self._G['tfm']['enum']['particle']['egg'] = 34
        self._G['tfm']['enum']['particle']['projection'] = 35
        self._G['tfm']['enum']['particle']['mouseTeleportation'] = 36
        self._G['tfm']['enum']['particle']['shamanTeleportation'] = 37
        self._G['tfm']['enum']['particle']['lollipopConfetti'] = 38
        self._G['tfm']['enum']['particle']['yellowCandyConfetti'] = 39
        self._G['tfm']['enum']['particle']['pinkCandyConfetti'] = 40
        
        self._G['tfm']['get']['room']['name'] = self.room.name
        self._G['tfm']['get']['room']['community'] = self.room.community
        self._G['tfm']['get']['room']['language'] = self.room.community
        self._G['tfm']['get']['room']['currentMap'] = self.room.mapCode
        self._G['tfm']['get']['room']['maxPlayers'] = self.room.roomDetails[8]
        self._G['tfm']['get']['room']['mirroredMap'] = self.room.mapInverted
        self._G['tfm']['get']['room']['uniquePlayers'] = len(self.room.clients)
        self._G['tfm']['get']['room']['passwordProtected'] = self.room.roomDetails[10] != ""
        self._G['tfm']['get']['room']['isTribeHouse'] = self.room.isTribeHouse

        self._G['tfm']['get']['room']['objectList'] = {}
        self._G['tfm']['get']['room']['playerList'] = {}

        for object in self.RoomObjects.values():
            self._G['tfm']['get']['room']['objectList'][object['id']] = {}
            self._G['tfm']['get']['room']['objectList'][object['id']]['id'] = object['id']
            self._G['tfm']['get']['room']['objectList'][object['id']]['type'] = object['type']
            self._G['tfm']['get']['room']['objectList'][object['id']]['angle'] = object['angle']
            self._G['tfm']['get']['room']['objectList'][object['id']]['ghost'] = object['ghost']
            self._G['tfm']['get']['room']['objectList'][object['id']]['vx'] = object['velX']
            self._G['tfm']['get']['room']['objectList'][object['id']]['vy'] = object['velY']
            self._G['tfm']['get']['room']['objectList'][object['id']]['x'] = object['posX']
            self._G['tfm']['get']['room']['objectList'][object['id']]['y'] = object['posY']
            self._G['tfm']['get']['room']['objectList'][object['id']]['rotationSpeed'] = object['rotationSpeed']
            self._G['tfm']['get']['room']['objectList'][object['id']]['stationary'] = object['stationary']

        for player in self.room.clients.values():
            self._G['tfm']['get']['room']['playerList'][player.playerName] = {}
            self._G['tfm']['get']['room']['playerList'][player.playerName]["community"] = player.langue.lower()
            self._G['tfm']['get']['room']['playerList'][player.playerName]["hasCheese"] = player.hasCheese
            self._G['tfm']['get']['room']['playerList'][player.playerName]["id"] = player.playerID
            self._G['tfm']['get']['room']['playerList'][player.playerName]["shamanMode"] = player.shamanType
            self._G['tfm']['get']['room']['playerList'][player.playerName]["inHardMode"] = player.shamanType
            self._G['tfm']['get']['room']['playerList'][player.playerName]["isDead"] = player.isDead
            self._G['tfm']['get']['room']['playerList'][player.playerName]["isFacingRight"] = player.isMovingRight
            self._G['tfm']['get']['room']['playerList'][player.playerName]["isJumping"] = player.isJumping
            self._G['tfm']['get']['room']['playerList'][player.playerName]["isShaman"] = player.isShaman
            self._G['tfm']['get']['room']['playerList'][player.playerName]["isVampire"] = player.isVampire
            self._G['tfm']['get']['room']['playerList'][player.playerName]["look"] = player.playerLook
            self._G['tfm']['get']['room']['playerList'][player.playerName]["movingLeft"] = player.isMovingLeft
            self._G['tfm']['get']['room']['playerList'][player.playerName]["movingRight"] = player.isMovingRight
            self._G['tfm']['get']['room']['playerList'][player.playerName]["playerName"] = player.playerName
            self._G['tfm']['get']['room']['playerList'][player.playerName]["registrationDate"] = player.regDate
            self._G['tfm']['get']['room']['playerList'][player.playerName]["score"] = player.playerScore
            self._G['tfm']['get']['room']['playerList'][player.playerName]["title"] = player.titleNumber

            self._G['tfm']['get']['room']['playerList'][player.playerName]["tribeName"] = player.tribeName
            self._G['tfm']['get']['room']['playerList'][player.playerName]["vx"] = player.velX
            self._G['tfm']['get']['room']['playerList'][player.playerName]["vy"] = player.velY
            self._G['tfm']['get']['room']['playerList'][player.playerName]["x"] = player.posX
            self._G['tfm']['get']['room']['playerList'][player.playerName]["y"] = player.posY
        self.UpdateLua(fnc2=self._G, to_update=self._globals)


    ### system. Functions
    def callback(self, function, *args):
        if '.' in function:
            fnc = self._G
            for f in function.split('.'):
                fnc = fnc[f]
        else:
            fnc = self._G[function]
        args = list(args)
        x = 0
        for i in args:
            temp = (self._globals.tostring(i) if self._globals.type(i) != "userdata" else "userdata")
            if "table" in temp:
                args[x] = dict(i)
            else:
                args[x] = i
            x+=1
        
        args = tuple(args)
        try:
            value = fnc(*args)
        except Exception as e:
            value = ""
        return value
        
    def random(self, start=0,end=0): 
        try:
            if end == 0:
                return random.randint(0,int(start))
            return random.randint(int(start),int(end))  
        except: 
            return random.randint(0,10)
        
    def luaEventLaunchInterval(self, minutes=45, seed=2):
        if self.CheckPerms("system.luaEventLaunchInterval"):
            if self.server.eventTimer != None: self.server.eventTimer.cancel()
            self.server.eventTimer = self.server.loop.call_later((minutes*60)-(random.randint(0,seed)*15), self.server.runEvent)

    def setLuaEventBanner(self, advID=0): ######
        return
        
    def giveAdventurePoint(self, playerName, advID, points):
        if self.CheckPerms("system.giveAdventurePoint"):
            player = self.room.clients.get(playerName)
            if player != None:
                player.aventurePoints[advID] += points
        
    def disableChatCommandDisplay(self, command="", hidden=True):
        if not command in self.HiddenCommands and hidden:
            self.HiddenCommands.append(self.FixUnicodeError(command))
        elif command in self.HiddenCommands and not hidden:
            self.HiddenCommands.remove(self.FixUnicodeError(command))
    
    def mkdir(self, names, name):
        try:
            import os
            os.mkdir(os.path.join(names, name), 0o6666)
        except:
            return

    def loadFile(self, id=0):
        if self.CheckPerms("system.loadFile"):
            name = self.owner.playerName if self.owner != None else self.room.minigame if self.room.minigame else "public"
            data = ""
            try:
                with open(f"./include/lua/playerDatas/module-team/{name}/{id}.lua", "r") as f:
                    data = f.read()
            except:
                self.mkdir("./include/lua/playerDatas/module-team/",name)
                with open(f"./include/lua/playerDatas/module-team/{name}/{id}.lua", "w") as f:
                    f.write(data)
            self.emit("FileLoaded", (id, data))
            return data != ""

    def loadPlayerData(self, playerName):
        if self.CheckPerms("system.loadPlayerData"):
            if "*" in playerName: 
                self.emit("PlayerDataLoaded", (playerName, ""))
                return False
            data = ""
            try:
                with open(f"./include/lua/playerDatas/{playerName}", "r") as f:
                    data = f.read()
            except:
                with open(f"./include/lua/playerDatas/{playerName}", "w") as f:
                    f.write(data)
            self.emit("PlayerDataLoaded", (playerName, data))
            return data != ""
        
    def newTimer(self, callback, _time, loop=False, *args):
        if self.CheckPerms("system.removeTimer"):
            _time = _time / 1000
            d = None
            if loop:
                self.lastloopid += 1
                d = self.createLoop(self.lastloopid, _time, lambda: callback(*args))
            else:
                self.lastloopid += 1
                d = self.server.loop.call_later(_time, lambda: callback(*args))
            self.loops[self.lastloopid] = d
            return self.lastloopid

    def removeTimer(self, _id):
        if self.CheckPerms("system.removeTimer"):
            _id = int(_id)
            while _id in self.loops:
                self.loops[_id].cancel()
                del self.loops[_id]

    def saveFile(self, data, id=0):
        if self.CheckPerms("system.saveFile"):
            name = self.owner.playerName if self.owner != None else self.room.minigame if self.room.minigame else "public"
            if len(data) > self.maxData:
                return False
            try:
                with open(f"./include/lua/playerDatas/module-team/{name}/{id}.lua", "a+") as f:
                    f.write(data)
            except:
                import os
                os.mkdir(os.path.join("./include/lua/playerDatas/module-team/", name), 0o6666)
                with open(f"./include/lua/playerDatas/module-team/{name}/{id}.lua", "a+") as f:
                    f.write(data)
            self.emit("FileSaved", (id))
            return True

    def savePlayerData(self, playerName, data):
        if self.CheckPerms("system.savePlayerData"):
            if len(data) > self.maxData:
                return
            with open(f"./include/lua/playerDatas/{playerName}", "a+") as f:
                f.write(data)

    ### ui. Functions
    def addLog(self, text, playerName=""):
        if self.CheckPerms("ui.addLog"):
            if playerName == "" and self.owner != None:
                self.owner.sendLogMessage(text)
            else:
                player = self.room.clients.get(self.server.players.get(Utils.parsePlayerName(playerName)))
                if player != None:
                    player.sendLogMessage(text)

    def setBackgroundColor(self, color="#6A7495"):
        self.client.sendPacket(Identifiers.send.Background_color, ByteArray().writeUTF(color).toByteArray())

    def setMapName(self, message=""):
        self.room.sendAll(Identifiers.send.Set_Map_Name, ByteArray().writeUTF(str(message)).toByteArray())
        
    def setShamanName(self, message=""):
        self.room.sendAll(Identifiers.send.Set_Shaman_Name, ByteArray().writeUTF(str(message)).toByteArray())

    ### tfm.exec. Functions
    def playSound(self, url, volume = 70, soundPosX=0, soundPosY=0, targetPlayer=""):
        p = ByteArray()
        p.writeUTF(url)
        p.writeShort(volume)
        p.writeBoolean(True)
        p.writeInt(soundPosX)
        p.writeInt(soundPosY)
        if targetPlayer == "" or not targetPlayer:
            self.room.sendAll(Identifiers.send.Play_Sound, p.toByteArray())
        else:
            player = self.room.clients.get(targetPlayer)
            if player != None:
                player.sendPacket(Identifiers.send.Play_Sound, p.toByteArray())
    
    def stopMusic(self,channel,targetPlayer=""):
        p = ByteArray()
        p.writeUTF(channel)
        p.writeByte(1) #? idk
        if targetPlayer == "" or not targetPlayer:
            self.room.sendAll([144,41], p.toByteArray())
        else:
            player = self.room.clients.get(targetPlayer)
            if player != None:
                player.sendPacket([144,41], p.toByteArray())
                
    def addBonus(self, type=1, x=0, y=0, id=0, angle=0, visible=True, targetPlayer=""):
        p = ByteArray()
        p.writeShort(x)
        p.writeShort(y)
        p.writeByte(type)
        p.writeShort(angle)
        p.writeInt(id)
        p.writeBoolean(visible)
        if targetPlayer == "" or not targetPlayer:
            self.room.sendAll(Identifiers.send.Skill_Object, p.toByteArray())
        else:
            player = self.room.clients.get(targetPlayer)
            if player != None:
                player.sendPacket(Identifiers.send.Skill_Object, p.toByteArray())

    def addConjuration(self, x, y, duration=10000):
        self.room.sendAll(Identifiers.old.send.Add_Conjuration, [x, y, duration])
        self.server.loop.call_later(duration / 1000, self.room.sendAll, Identifiers.old.send.Conjuration_Destroy, [int(x), int(y)])

    def addImage(self, imageName = "", target = "", xPosition = 50, yPosition = 50, targetPlayer = "", scaleX = 1, scaleY = 1,angle = 0,alpha = 1,AnchorX=0,AnchorY=0):
        if imageName is None:
            imageName = ""
        if target is None:
            target = ""
        if xPosition is None:
            xPosition == 50
        if yPosition is None:
            yPosition = 50
        if targetPlayer is None:
            targetPlayer = ""
        if scaleX is None:
            scaleX = 1
        if scaleY is None:
            scaleY = 1
        if angle is None:
            angle = 0
        if alpha is None:
            alpha = 1
        if AnchorX is None:
            AnchorX = 0
        if AnchorY is None:
            AnchorY = 0
        packet = ByteArray()
        self.room.lastImageID += 1
        packet.writeInt(self.room.lastImageID)
        self.imagesadd.append(self.room.lastImageID)
        packet.writeUTF(imageName)
        packet.writeByte(1 if target.startswith("#") else 2 if target.startswith("$") else 3 if target.startswith("%") else 4 if target.startswith("?") else 5 if target.startswith("_") else 6 if target.startswith("!") else 7 if target.startswith("&") else 8 if target.startswith(":") else 9 if target.startswith("+") else 0)
        while not target[:1].isdigit(): target = target[1:]
        if '.0' in target: target = target.split('.')[0]
        packet.writeInt(int(target) if target.isdigit() else self.server.getPlayerCode(Utils.parsePlayerName(target)))
        packet.writeShort(xPosition)
        packet.writeShort(yPosition)
        packet.writeFloat(scaleX)
        packet.writeFloat(scaleY)
        packet.writeFloat(angle)
        packet.writeFloat(alpha)
        packet.writeFloat(AnchorX)
        packet.writeFloat(AnchorY)
        packet.writeByte(0)
        if targetPlayer == "":
            self.room.sendAll(Identifiers.send.Add_Image, packet.toByteArray())
        else:
            player = self.room.clients.get(Utils.parsePlayerName(targetPlayer))
            if player != None:
                player.sendPacket(Identifiers.send.Add_Image, packet.toByteArray())
        return self.room.lastImageID
    def addJoint(self, id=0, ground1=0, ground2=0, jointDefinition={}):
        p = ByteArray()
        p.writeShort(id)
        p.writeShort(ground1)
        p.writeShort(ground2)
        jointDefinition=dict(jointDefinition)
        p.writeByte(jointDefinition.get('type',0))
        for name in ['point1','point2','point3','point4']:
            p.writeBoolean(bool(jointDefinition.get(name,False)))
            try:
                p.writeShort(int(jointDefinition[name].replace(' ','').split(',')[0]))
                p.writeShort(int(jointDefinition[name].replace(' ','').split(',')[1]))
            except:
                p.writeShort(0)
                p.writeShort(0)
        p.writeShort(jointDefinition.get('frequency',0) * 100)
        p.writeShort(jointDefinition.get('damping',0) * 100)
        p.writeBoolean(False if [i in jointDefinition for i in ['line','color','alpha','foreground']] == [False, False, False, False] else True)
        p.writeShort(jointDefinition.get('line',0))
        p.writeInt(int(jointDefinition.get('color',0)))
        p.writeShort(jointDefinition.get('alpha',1) * 100)
        p.writeBoolean(jointDefinition.get('foreground',False))
        try:
            p.writeShort(int(jointDefinition['axis'].replace(' ','').split(',')[0]))
            p.writeShort(int(jointDefinition['axis'].replace(' ','').split(',')[1]))
        except:
            p.writeShort(0)
            p.writeShort(0)
        p.writeBoolean(bool(jointDefinition.get('angle',False)))
        p.writeShort(jointDefinition.get('angle',0))
        for name in ['limit1','limit2','forceMotor','speedMotor']:
            p.writeBoolean(bool(jointDefinition.get(name,False)))
            p.writeShort(jointDefinition.get(name,0) * 100)
        p.writeShort(jointDefinition.get('ratio',1) * 100)
        self.room.sendAll(Identifiers.send.Add_Joint, p.toByteArray())

    def addShamanObject(self, type=0, x=0, y=0, angle=0, vx=0, vy=0, ghost=False, options={}):
        self.LastRoomObjectID += 1
        _id = self.LastRoomObjectID
        self.RoomObjects[_id] = {'id': _id, 'type': type, 'angle': angle, 'ghost': ghost, 'velX': vx, 'velY': vy, 'posX': x, 'posY': y, 'rotationSpeed':(vx+vy)/2, 'stationary': (vx == 0 and vy == 0)}
        self.RefreshTFMGet()
        p = ByteArray()
        p.writeInt(_id)
        p.writeShort(type)
        p.writeShort(x)
        p.writeShort(y)
        p.writeShort(angle)
        p.writeByte(vx)
        p.writeByte(vy)
        p.writeBoolean(not ghost)
        p.writeByte(0)
        p.writeInt(options["fixedXSpeed"] if "fixedXSpeed" in options else 0)
        p.writeInt(options["fixedYSpeed"] if "fixedYSpeed" in options else 0)
        self.room.sendAll(Identifiers.send.Spawn_Object, p.toByteArray())
        return _id

    def attachBalloon(self, playerName, isAttached=True, colorType=1, ghost=False, speed=1):
        colorType = 4 if colorType > 4 else 1 if colorType < 1 else colorType
        player = self.server.players.get(Utils.parsePlayerName(playerName))
        if player != None:
            p = self.room.objectID + 1
            player.sendPlaceObject(p,28,player.posX,player.posY-25,0,0,0,not ghost,True,colorType)
            if isAttached:
                self.room.sendAll(Identifiers.send.SetPositionToAttach, ByteArray().writeByte(-1).toByteArray())
                self.room.sendAll(Identifiers.send.AttachPlayer, ByteArray().writeInt(player.playerCode).writeInt(p).writeInt(speed*1000).toByteArray())
            else:
                self.room.sendAll(Identifiers.send.UnAttachPlayer, ByteArray().writeInt(player.playerCode).toByteArray())

    def changePlayerSize(self, name, size=1):
        size = float(size)
        size = 5.0 if size > 5.0 or size < 0.1 else size
        size = int(size * 100)
        player = self.server.players.get(Utils.parsePlayerName(name))
        if player != None:
            self.room.sendAll(Identifiers.send.Mouse_Size, ByteArray().writeInt(player.playerCode).writeShort(size).writeBoolean(False).toByteArray())

    def chatMessage(self, message, target=""):
        if self.CheckPerms("tfm.exec.chatMessage") == True:
            if target == "":
                for player in self.room.clients.values():
                    player.sendMessage(self.FixUnicodeError(message))
            else:
                player = self.room.clients.get(target)

                if player != None:
                    player.sendMessage(self.FixUnicodeError(message))

    def disableAfkDeath(self, status=True):
        self.room.disableAfkKill = status
        
    def disableAllShamanSkills(self, status=True):
        self.room.roomDetails[1] = int(status)

    def disableAutoNewGame(self, status=True):
        self.room.isFixedMap = status
        
    def disableAutoScore(self, status=True):
        self.room.noAutoScore = status

    def disableAutoShaman(self, status=True):
        self.room.noShaman = status

    def disableAutoTimeLeft(self, status=True):
        self.room.never20secTimer = status
    
    def disableDebugCommand(self, status=True):
        self.room.disableDebugCommand = status
        self.room.sendAll(Identifiers.send.Lua_Disable, ByteArray().writeBoolean(self.room.disableWatchCommand).writeBoolean(self.room.disableDebugCommand).writeBoolean(self.room.disableMinimalistMode).toByteArray())
    
    def disableMinimalistMode(self, status=True):
        self.room.disableMinimalistMode = status
        self.room.sendAll(Identifiers.send.Lua_Disable, ByteArray().writeBoolean(self.room.disableWatchCommand).writeBoolean(self.room.disableDebugCommand).writeBoolean(self.room.disableMinimalistMode).toByteArray())
    
    def disableMortCommand(self, status=True):
        self.room.disableMortCommand = status
        
    def disableWatchCommand(self, status=True):
        self.room.disableWatchCommand = status
        self.room.sendAll(Identifiers.send.Lua_Disable, ByteArray().writeBoolean(self.room.disableWatchCommand).writeBoolean(self.room.disableDebugCommand).writeBoolean(self.room.disableMinimalistMode).toByteArray())
    
    def disablePhysicalConsumables(self, status=True):
        self.room.roomDetails[2] = status
    
    def displayParticle(self, particleType, xPosition, yPosition, xSpeed=0, ySpeed=0, xAcceleration=0, yAcceleration=0, targetPlayer=""):
        packet = ByteArray()
        packet.writeByte(particleType)
        packet.writeShort(xPosition)
        packet.writeShort(yPosition)
        packet.writeShort(xSpeed)
        packet.writeShort(ySpeed)
        packet.writeShort(xAcceleration)
        packet.writeShort(yAcceleration)
        if targetPlayer == "":
            self.room.sendAll(Identifiers.send.Display_Particle, packet.toByteArray())
        else:
            player = self.server.players.get(Utils.parsePlayerName(targetPlayer))
            if player != None:
                player.sendPacket(Identifiers.send.Display_Particle, packet.toByteArray())

    def explosion(self, x, y, power, distance, miceOnly=False):
        for player in self.server.players.values():
            player.sendPacket([5, 17], [int(x), int(y), int(power), int(distance), bool(miceOnly)])

    def freezePlayer(self, playerName, freeze=True, displayIce=True):
        player = self.room.clients.get(Utils.parsePlayerName(playerName))
        if player:
            player.sendPacket(Identifiers.send.Stop_Moving, ByteArray().writeBoolean(freeze).writeBoolean(displayIce).toByteArray())

    def getPlayerSync(self):
        if self.CheckPerms("tfm.exec.getPlayerSync") == True and self.owner != None:
            self.chatMessage("Current Sync: "+self.room.currentSyncName, self.owner.playerName)
            return self.room.currentSyncName

    def giveCheese(self, target):
        player = self.room.clients.get(Utils.parsePlayerName(target))
        if player != None and not player.isDead and not player.hasCheese:
            player.sendGiveCheese(0)

    def giveConsumables(self, playerName, consumableId, amount=1):
        if self.CheckPerms("tfm.exec.giveConsumables"):
            player = self.room.clients.get(Utils.parsePlayerName(playerName))
            if player:
                player.giveConsumable(consumableId, amount)

    def giveMeep(self, target, status=True):
        player = self.room.clients.get(Utils.parsePlayerName(target))
        if player != None and not player.isDead:
            player.sendPacket(Identifiers.send.Can_Meep, status)

    def giveTransformations(self, target, status=True):
        player = self.room.clients.get(Utils.parsePlayerName(target))
        if player != None:
            player.sendPacket(Identifiers.send.Can_Transformation, int(status))
            player.hasLuaTransformations = status

    def killPlayer(self, target):
        player = self.room.clients.get(Utils.parsePlayerName(target))
        if not player.isDead:
            player.isDead = True
            if player.room.noAutoScore:
                player.playerScore += 1
            player.sendPlayerDied()
            player.room.checkChangeMap()

    def linkMice(self, Name, Target, status=True):
        player = self.server.players.get(Utils.parsePlayerName(Name))
        player1 = self.server.players.get(Utils.parsePlayerName(Target))
        if player != None and player1 != None:
            self.room.sendAll(Identifiers.send.Soulmate, ByteArray().writeBoolean(status).writeInt(player.playerCode).writeInt(player1.playerCode if status else -1).toByteArray())

    def lowerSyncDelay(self, playerName):
        if self.CheckPerms("tfm.exec.lowerSyncDelay") == True:
            player = self.server.players.get(Utils.parsePlayerName(playerName))
            if player != None:
                player.sendPacket(Identifiers.send.Lower_Sync_Delay, [player.playerName])

    def moveCheese(self, x, y):
        self.room.sendAll(Identifiers.old.send.Move_Cheese, [x, y])
            
    def moveObject(self, id, xy, vy, dat=False, x=0, y=0, r=False, i=0, b=False):
        self.RoomObjects[id]['velX'] = x
        self.RoomObjects[id]['velY'] = y
        self.RoomObjects[id]['posX'] = xy
        self.RoomObjects[id]['posY'] = vy
        self.RoomObjects[id]['angle'] = i
        self.RefreshTFMGet()
        packet = ByteArray()
        packet.writeInt(id)
        packet.writeShort(xy)
        packet.writeShort(vy)
        packet.writeBoolean(dat)
        packet.writeShort(x)
        packet.writeShort(y)
        packet.writeBoolean(r)
        packet.writeShort(i)
        packet.writeBoolean(b)
        self.room.sendAll(Identifiers.send.Move_Object, packet.toByteArray())

    def newGame(self, mapCode="", mirroredMap=False):
        self.room.forceNextMap = str(mapCode)
        self.room.mapInverted = mirroredMap
        self.room.canChangeMap = True
        self.server.loop.create_task(self.room.mapChange())

    def playEmote(self, playerName, emoteId, emoteArg=""):
        player = self.room.clients.get(Utils.parsePlayerName(playerName))
        if player:
            player.sendPlayerEmote(emoteId, emoteArg, False, True)

    def playerVictory(self, target):
        player = self.room.clients.get(Utils.parsePlayerName(playerName))
        if player != None and not player.isDead:
            if not player.hasCheese:
                self.giveCheese(playerName)
            player.server.loop.create_task(player.playerWin(1, 0))

    def removeBonus(self, id=0, targetPlayer=""):
        p = ByteArray().writeInt(id)
        if targetPlayer == "":
            self.room.sendAll([5, 15], p.toByteArray())
        else:
            player = self.room.clients.get(Utils.parsePlayerName(targetPlayer))
            if player != None:
                player.sendPacket([5, 15], p.toByteArray())
              
    def removeCheese(self, target):
        player = self.room.clients.get(Utils.parsePlayerName(playerName))
        if player != None and not player.isDead and player.hasCheese:
            player.hasCheese = False
            player.sendRemoveCheese()
              
    def removeImage(self, imageId=0, targetPlayer="", visible=False, fadeIn=0, fadeOut=0):
        if not isinstance(targetPlayer, str): targetPlayer = ""
        if targetPlayer == "":
            self.room.sendAll(Identifiers.send.Remove_Image, ByteArray().writeInt(imageId).writeBoolean(visible).toByteArray())
        else:
            player = self.room.clients.get(Utils.parsePlayerName(targetPlayer))
            if player != None:
                player.sendPacket(Identifiers.send.Remove_Image, ByteArray().writeInt(imageId).writeBoolean(visible).toByteArray())
        if imageId in self.imagesadd: self.imagesadd.remove(imageId)
        
    def removeJoint(self, id):
        self.room.sendAll(Identifiers.send.Remove_Joint, [id])
        
    def RemovePhysicObject(self, id):
        self.room.sendAll(Identifiers.send.Remove_Physic_Object, [id])

    def respawnPlayer(self, playerName):
        player = self.room.clients.get(Utils.parsePlayerName(playerName))
        if player != None:
            self.room.respawnSpecific(playerName)

    def setAieMode(self, enabled=True, sensibility=1, targetPlayer=""):
        if targetPlayer == "":
            self.room.sendAll(Identifiers.send.setAIEMode, ByteArray().writeBoolean(enabled).writeEncoded(sensibility * 1000).toByteArray())
        else:
            player = self.room.clients.get(Utils.parsePlayerName(targetPlayer))
            if player != None:
                player.sendPacket(Identifiers.send.setAIEMode, ByteArray().writeBoolean(enabled).writeEncoded(sensibility * 1000).toByteArray())

    def setAutoMapFlipMode(self, status=False):
        self.room.autoMapFlipMode = status

    def setGameTime(self, time=0, add=False):
        if str(time).isdigit():
            if add:
                iTime = self.room.roundTime + (self.room.gameStartTime - Utils.getTime()) + self.room.addTime + int(time)
            else:
                iTime = int(time)
            iTime = 5 if iTime < 5 else (32767 if iTime > 32767 else iTime)
            for player in self.room.clients.values():
                player.sendRoundTime(iTime)

            self.room.roundTime = iTime
            self.room.changeMapTimers(iTime)

    def setPlayerGravityScale(self, playerName, scale=1, windScale=1):
        player = self.room.clients.get(Utils.parsePlayerName(playerName))
        if player != None:
            self.room.sendAll(Identifiers.send.PlayerScale, ByteArray().writeEncoded(player.playerCode).writeEncoded(scale * 1000).writeEncoded(windScale * 1000).toByteArray())

    def setPlayerNightMode(self, enable=True, playerName=""):
        if playerName == "":
            self.room.sendAll(Identifiers.send.NightMode, ByteArray().writeBoolean(enable).toByteArray())
        else:
            player = self.room.clients.get(Utils.parsePlayerName(playerName))
            if player != None:
                player.sendPacket(Identifiers.send.NightMode, ByteArray().writeBoolean(enable).toByteArray())

    def setPlayerScore(self, playerName, score, amount=False):
        if amount is None:
            amount = False
        player = self.room.clients.get(Utils.parsePlayerName(playerName))
        if player:
            if amount:
                player.playerScore += score
            else:
                player.playerScore = score
            self.room.sendAll(Identifiers.send.Set_Player_Score, ByteArray().writeInt(player.playerCode).writeShort(player.playerScore).toByteArray())

    def setPlayerSync(self, playerName):
        if self.CheckPerms("tfm.exec.setPlayerSync") == True:
            player = self.room.clients.get(Utils.parsePlayerName(playerName))
            if player != None:
                player.isSync = True
                self.room.currentSyncCode = player.playerCode
                self.room.currentSyncName = player.playerName
                if self.owner != None:
                    self.chatMessage("New Sync: "+str(player.playerName), self.owner.playerName)

    def setRoomMaxPlayers(self, maxPlayers):
        if self.CheckPerms("tfm.exec.setRoomMaxPlayers") == True:
            if maxPlayers > 0:
                self.room.roomDetails[8] = maxPlayers

    def setRoomPassword(self, password):
        if self.CheckPerms("tfm.exec.setRoomPassword"):
            self.room.roomDetails[10] = password if len(password) > 0 else ""

    def setShaman(self, target, makeAShaman=True):
        player = self.room.clients.get(Utils.parsePlayerName(target))
        if player != None:
            player.isShaman = True
            self.room.sendAll(Identifiers.send.New_Shaman, ByteArray().writeInt(player.playerCode).writeByte(player.shamanType).writeShort(player.shamanLevel).writeShort(player.Skills.getShamanBadge()).toByteArray())

    def setVampirePlayer(self, playerName, status=True):
        player = self.room.clients.get(Utils.parsePlayerName(playerName))
        if player != None:
            player.sendVampireMode(status)
            
    def setWorldGravity(self, x=0, y=10):
        if y == 0:
            self.room.sendAll(Identifiers.old.send.Gravity, [x, 8])
        else:
            self.room.sendAll(Identifiers.old.send.Gravity, [x, y])
    
    def snow(self, time=60, power=10):
        self.room.startSnow(time, power, not self.room.isSnowing)
        
    ### Others

                        
    def emit(self, eventName="", args=()):
        if self.runtime is None:
            return

        self.RefreshTFMGet()
        if eventName == "NewGame":
            self.RoomObjects = {}
            #self.SetupRuntimeGlobals()

        if type(args) == tuple:
            args_strPack = ""

            for x in args:
                args_strPack += (str(x) if type(x) != str and type(x) != bool else '"%s"' % (x) if type(x) != bool else ("true" if x else "false")) + ","
        else:
            args_strPack = (str(args) if type(args) != str and type(args) != bool else '"%s"' % (args) if type(args) != bool else ("true" if args else "false")) + ","

        try:
            self.runtime.execute("if(event%s)then event%s(%s) end" % (str(eventName), str(eventName), args_strPack[:-1]))
        except Exception as error:
            if not self.owner is None:
                self.owner.sendLuaMessage("[<V>%s.lua</V>][<N>%s</N>] <BL>%s</BL>" % (self.owner.playerName, str(time.strftime("%H:%M:%S")), str(error)))
   
    def stopModule(self, playerName="", action=0): ##############
        self.room.isMinigame = False
        self.room.minigame = None
        self.runtime = None
        self.running = False
        self.room.luaRuntime = None
        self.room.isEvent = False
        #self.room.startSnow(0, 10, False)

        if self.room.isTribeHouse:
            self.room.countStats = False
            self.room.isTribeHouse = True
            self.room.autoRespawn = True
            self.room.never20secTimer = True
            self.room.noShaman = True
            self.room.disableAfkKill = True
            self.room.isFixedMap = True
            self.room.roundTime = 0

        if self.room.changeMapTimer != None:
            self.room.changeMapTimer.cancel()
        self.room.changeMapTimers(5)
        self.room.canChangeMap = True
        self.server.loop.create_task(self.room.mapChange(True))

        if self.LastRoomObjectID > 2000:
            while self.LastRoomObjectID > 2000:
                self.room.removeObject(self.LastRoomObjectID)
                self.LastRoomObjectID -= 1

        for i in self.imagesadd:
            self.removeImage(i)

        for _id in self.loops:
            self.loops[_id].cancel()

        self.imagesadd = []
        self.loops = {}

        if playerName != "" and not self.room.minigame is None:
            if not self.room.minigame.owner is None:
                self.room.minigame.owner.sendLuaMessage("[<V>%s.lua</V>][<N>%s</N>] %s by: <J>%s</J>" % (playerName, str(time.strftime("%H:%M:%S")), "Module stopped" if action == 0 else "Another module was loaded", str(playerName)))

    def RunCode(self, code=""):
        #if self.running:
            #self.stopModule()
        if self.owner != None:
            for while_stmt in re.findall('while[\s+(].*[\s+)]do', code):
             id = int(time.time())
             code = code.replace(while_stmt, """
                 local __while__%s = {
                     time = os.time() +  0.4,
                     callback = function(self)
                         if (os.time() - self.time >= 0) then
                             error("Lua destroyed: Runtime Too Long")
                         end 
                        
                         return (%s)
                     end
                 }
                 while(__while__%s:callback())do""" % (id, while_stmt[5:-2], id))
        if self.runtime == None:
            self.runtime = LuaRuntime(unpack_returned_tuples=True)
            self.SetupRuntimeGlobals()
        try:
            ts = time.time()
            self.runtime.execute(code)
            self.EventLoop()
            te = time.time() - ts
            if self.owner != None:
                self.owner.sendLuaMessage(f"[<V>{self.owner.roomName}</V>] [{self.owner.playerName}] Script loaded in {math.ceil(te*1000)} ms. (4000 max)")
            self.script = code
        except Exception as error:
            self.script = ""
            if self.owner != None:
                self.owner.sendLuaMessage(f"[<V>{self.owner.roomName}</V>] [{self.owner.playerName}] {error}")