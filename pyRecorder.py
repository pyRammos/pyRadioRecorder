import sys
# import vlc
import datetime
from time import sleep
import owncloud
import paramiko
import os
import urllib.request
import configparser
import sys
import shutil
import ffmpy3

def getSetting(section, setting):
    config = configparser.ConfigParser()
    config.read('settings.cfg')
    if section not in config.sections():
       # print("Section " + section + " not found. Will try DEFAULT")
        section = "DEFAULT"
    try:
        #print ("Setting " + setting + " to " + config[section][setting])
        return config[section][setting]
    except:
        print ("Key " + setting + " not found in section "+ section)

def debug(message):
    print (str(datetime.datetime.now()) + " --::-- " + str(message))

name = ""
duration = -1
toOwncloud = False
toPodcast = False
toLocal = False

if len (sys.argv) <2:
    debug  ("You have not passed enough arguments")
    debug ("Usage: pyRecord name=NAME duration=DURATION_IN_SECONDS [toOwncloud] [toPodcast] [toLocal]")

    exit (1)
for param in sys.argv:
    #print (param)
    if "name" in str(param).lower():
        #print ("Found Name : " +  str(param).lower().strip("name="))
        name = param[5:]
    if "duration" in str(param).lower():
        #print ("Found Duration of "+  str(param).lower().strip("duration="))
        try:
            duration = int(str(param).lower().strip("duration="))
        except:
            debug ("Duration must be a number, eg duration=3660")
            debug ("Usage: pyRecord [name=NAME] duration=DURATION_IN_SECONDS [toOwncloud] [toPodcast] [toLocal]")
            exit(1)
    if "toowncloud" in str(param).lower():
        #print("Will upload to ouwncloud")
        toOwncloud=True
    if "topodcast" in str(param).lower():
        #print("Will upload to podcast")
        toPodcast = True
    if "tolocal" in str(param).lower():
        #print("Will upload to podcast")
        toLocal = True
if name=="":
    debug ("You must specify a name, e.g. name=myShow")
    debug ("Usage: pyRecord [name=NAME] duration=DURATION_IN_SECONDS [toOwncloud] [toPodcast] [toLocal]")
    exit(1)

if duration <=0 :
    debug ("I do need the duration of the clip you want me to record. Don't make me guess ...")
    debug ("Usage: pyRecord name=NAME duration=DURATION_IN_SECONDS [toOwncloud] [toPodcast] [toLocal]")
    exit (1)

stream = ""
ocuser= ""
ocpass = ""
ocurl = ""
ocbasedir = ""
sshuser = ""
sshpass = ""
sshserver = ""
sshpath = ""
podcastrefreshurl=""
trimstart = 0
savelocation = ""

stream = getSetting(name.upper(),"stream")
if stream=="":
    debug ("Cannot determine stream url. Set the stream parameter in the settings file. Goodbye")
    exit (1)
if toOwncloud:
    ocuser = getSetting(name.upper(), "user")
    ocpass = getSetting(name.upper(), "password")
    ocurl = getSetting(name.upper(), "url")
    ocbasedir = getSetting(name.upper(), "ocbasedir")
    if ocuser == "" or ocpass=="" or ocurl == "":
        debug ("You want to upload to owncloud but owncloud settings in the config file are incomplete")
        debug ("Set the user, password, url and ocbasedir key/values")
        debug ("Good bye")
        exit (1)

if toPodcast:
    sshuser = getSetting(name.upper(),"user")
    sshpass = getSetting(name.upper(),"password")
    sshserver = getSetting(name.upper(),"server")
    sshpath = getSetting(name.upper(),"podcastpath")
    podcastrefreshurl = getSetting(name.upper(), "podcastrefreshurl")
    if sshuser=="" or sshpass=="" or sshserver=="" or podcastrefreshurl=="":
        debug ("You want to upload to podcast generator but settings in the config file are incomplete")
        debug ("Set the user, password, server, podcastpath and podcastrefreshurl key/values")
        debug ("Good bye")
if toLocal:
    savelocation = getSetting(name.upper(), "saveto")
    if savelocation=="":
        debug ("You want to save the file to local/mounted filesystems but settings in the config file are incomplete")
        debug ("Please set the savelocation key/value under the "+name+" section")
        debug ("Good bye")
        exit (1)
        debug ("Will save to " + str(savelocation))

trimstart = int(getSetting(name.upper(),"trimstart"))
recordatleast = duration
reduceby = trimstart #seconds to slice off the beginning

now = datetime.datetime.now()
end = now + datetime.timedelta(seconds=recordatleast)
today = now.isoformat()
today = str(today[:10]).replace("-","")
today = today[2:]
today = today +"-"+ now.strftime('%a')
streamName = name
filename = streamName + today + ".mp3"
targetdir = "/" + streamName +"/" + str(now.year) + "/" + str(now.month) + " - " + str(now.strftime("%b"))
debug ("Starting at " + str(now))
debug ("Will stop at " + str(end))
#parameters = "sout=#transcode{acodec=mp4a,channels=2,ab=64,samplerate=44100}:duplicate{dst=std{access=file,mux=mp4,dst='"+filename+"'"
#caching_parameters ="--network-caching=5000"
#reconnect_parameters = "--http-reconnect"
#quiet_parameters = "--quiet"
oclocation = ocbasedir+ targetdir + "/"
#instance = vlc.Instance()
#player = instance.media_player_new()
#media = instance.media_new(stream, parameters, caching_parameters, reconnect_parameters, quiet_parameters)
#media.get_mrl()
#player.set_media(media)
title = filename.replace(".mp3", "")
artist = streamName
genre = "radio"
album = streamName
try:
    debug ("Recording from " + stream + " for " + str(recordatleast))
    #ff = ffmpy3.FFmpeg(inputs={stream: None}, outputs={filename: '-y -acodec copy -t ' + str("recordatleast") + ' -metadata title=' + str(title) + ' -metadata artist=' +  str(artist) + ' -metadata genre=' + str(genre) + ' -metadata album=' + str(album)})
    ff = ffmpy3.FFmpeg(inputs={stream: None}, outputs={
        filename: '-y -acodec copy -t '+ str(recordatleast) +' -metadata title=' + str(filename) + ' -metadata artist=' + str(artist) + ' -metadata genre=' + str(genre) + ' -metadata album=' + str(album)})
    debug ("Command = " +ff.cmd)
    ff.run()
except Exception as e:
    debug ("Cannot record from that stream")
    debug ("Error = " + str(e))
    debug ("/OpensWindowAndJumpsOut")
    exit (2)


if toOwncloud:
    debug ("Uploading to OwnCloud")
    oc = owncloud.Client(ocurl)
    oc.login(ocuser, ocpass)
    dirs = oclocation.split("/")
    dirtocreate = ""
    for x in dirs:
        dirtocreate = dirtocreate + x + "/"
        try:
            oc.mkdir(dirtocreate)
        except:
            debug ("Cannot create OwnCloud Dir, possibly because it exists already")

    try:
        oc.put_file(oclocation + filename, filename)
    except Exception as e:
        debug ("Error ="  + e)
        debug ("Could not upload file. Go figure ...")

if toPodcast:
    debug ("Uploading file to podcast")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(sshserver, username=sshuser, password=sshpass)
    sftp = ssh.open_sftp()
    sftp.put(filename, sshpath + filename)
    sftp.close()
    ssh.close()

    debug ("Refreshing Podcasts")
    contents = urllib.request.urlopen(podcastrefreshurl).read()
if toLocal:
    debug ("Saving to local location")
    debug ("will make dir " + savelocation + targetdir)
    try:
        os.makedirs(savelocation + targetdir)
    except Exception as e:
        debug("Error: " + str(e))
        debug ("Could not create local dir, possibly because it exists")
    try:
        shutil.copyfile (filename, savelocation + targetdir+"/"+filename)
    except Exception as e:
        debug ("Error =" + str(e))
        debug ("Could not copy file")
debug ("Deleting local files")

os.remove(filename)


exit(0)



