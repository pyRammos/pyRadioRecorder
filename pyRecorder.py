import sys
# import vlc
import datetime
from time import sleep
import owncloud
import paramiko
import os
import http.client, urllib
import urllib.request
import configparser
import sys
import shutil
import ffmpy3
import ssl
import logging
#from pushover import Client

def getSetting(section, setting):
    config = configparser.ConfigParser()
    try:
        config.read('settings.cfg')
    except Exception as e:
        debug("Error: Cannot read settings.cfg: " + str(e))
        error=True
    #section = "DEFAULT"
    try:
        #print ("Setting " + setting + " to " + config[section][setting])
        return config[section][setting]
    except:
        print ("Key " + setting + " not found in section "+ section + ".")

def debug(message):
    print (str(datetime.datetime.now()) + " --::-- " + str(message))
    logging.debug(str(message))

error=False
name = ""
duration = -1
toOwncloud = False
toPodcast = False
toLocal = False
toSSH = False
toLocalFlat = False
notify = False

logging.basicConfig(filename= "recorder.txt", level=logging.DEBUG,format="%(asctime)s %(message)s")
debug ("INFO: ============ New Start ============")


if len (sys.argv) <2:
    debug  ("ERROR: You have not passed enough arguments")
    debug ("Usage: pyRecord name=NAME duration=DURATION_IN_SECONDS [toOwncloud] [toPodcast] [toLocal] [toLocalFlat] [toSSH]")

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
            debug ("ERROR: Duration must be a number, eg duration=3660")
            debug ("Usage: pyRecord [name=NAME] duration=DURATION_IN_SECONDS [toOwncloud] [toPodcast] [toLocal] [toLocalFlat] [toSSH]")
            exit(1)
    if "toowncloud" in str(param).lower():
        debug("INFO: Will upload to ouwncloud")
        toOwncloud=True
    if "topodcast" in str(param).lower():
        debug("INFO: Will upload to podcast")
        toPodcast = True
    if "tolocal" in str(param).lower():
        debug("INFO: Will save locally (with folder structure)")
        toLocal = True
    if "tossh" in str(param).lower():
        debug("INFO: Will upload via SSH")
        toSSH = True
    if "tolocalflat" in str(param).lower():
        debug("INFO: Will save locally without folder structure")
        toLocalFlat = True
    
    if "notify" in str(param).lower():
        debug("INFO: Will notify via Pushover")
        notify = True
 
if name=="":
    debug ("You must specify a name, e.g. name=myShow")
    debug ("Usage: pyRecord [name=NAME] duration=DURATION_IN_SECONDS [toOwncloud] [toPodcast] [toLocal] [toLocalFlat] [toSSH]")
    exit(1)

if duration <=0 :
    debug ("ERROR: I do need the duration of the clip you want me to record. Don't make me guess ...")
    debug ("Usage: pyRecord name=NAME duration=DURATION_IN_SECONDS [toOwncloud] [toPodcast] [toLocal] [toLocalFlat] [toSSH]")
    exit (1)

if toPodcast:
    if  not (toLocal or toSSH):
        debug ("ERROR: You want to upload this to a podcas generator, but have not set toLocal or toSSH")
        debug ("Usage: pyRecord name=NAME duration=DURATION_IN_SECONDS [toOwncloud] [toPodcast] [toLocal] [toLocalFlat] [toSSH]")
        exit (1)
stream = ""
ocuser= ""
ocpass = ""
ocurl = ""
ocbasedir = ""
oclocation = ""
sshuser = ""
sshpass = ""
sshserver = ""
sshkeyfile =""
sshpath = ""
podcastrefreshurl=""
trimstart = 0
savelocation = ""
saveToFlat=""
pushovertoken = ""

stream = getSetting(name.upper(),"stream")
if stream=="" or stream==None:
    debug ("ERROR: Cannot determine stream url. Set the stream parameter in the settings file. Goodbye")
    exit (1)
if toOwncloud:
    ocuser = getSetting(name.upper(), "ocuser")
    ocpass = getSetting(name.upper(), "ocpass")
    ocurl = getSetting(name.upper(), "ocurl")
    ocbasedir = getSetting(name.upper(), "ocbasedir")
    if ocuser == "" or ocpass=="" or ocurl == "":
        debug ("ERROR: You want to upload to owncloud but owncloud settings in the config file are incomplete")
        debug ("Set the user, password, url and ocbasedir key/values")
        debug ("Good bye")
        exit (1)

if toPodcast:
    sshuser = getSetting(name.upper(),"sshuser")
    sshpass = getSetting(name.upper(),"sshpassword")
    sshkeyfile = getSetting(name.upper(),"sshkeyfile")
    sshserver = getSetting(name.upper(),"sshserver")
    sshpath = getSetting(name.upper(),"sshpath")
    podcastrefreshurl = getSetting(name.upper(), "podcastrefreshurl")
    if sshuser=="" or (sshpass=="" and sshkeyfile=="")or sshserver=="" or podcastrefreshurl=="":
        debug ("ERROR: You want to upload to podcast generator but settings in the config file are incomplete")
        debug ("Set the user, password (or key file), server, podcastpath and podcastrefreshurl key/values")
        debug ("Good bye")
        exit(1)
if toLocal:
    savelocation = getSetting(name.upper(), "saveto")
    if savelocation=="":
        debug ("ERROR: You want to save the file to local/mounted filesystems but settings in the config file are incomplete")
        debug ("Please set the savelocation key/value under the "+name+" section")
        debug ("Good bye")
        exit (1)
        debug ("INFO: Will save to " + str(savelocation))

if toLocalFlat:
    saveToFlat = getSetting(name.upper(), "savetoflat")
    if saveToFlat=="":
        debug ("ERROR: You want to save the file to local/mounted filesystems but settings in the config file are incomplete")
        debug ("Please set the savetoflat key/value under the "+name+" section")
        debug ("Good bye")
        exit (1)
        debug ("INFO: Will save to " + str(savelocation))

# trimstart = int(getSetting(name.upper(),"trimstart"))
recordatleast = duration
# reduceby = trimstart #seconds to slice off the beginning

now = datetime.datetime.now()
end = now + datetime.timedelta(seconds=recordatleast)
today = now.isoformat()
today = str(today[:10]).replace("-","")
today = today[2:]
today = today +"-"+ now.strftime('%a')
streamName = name
filename = streamName + today + ".mp3"
targetdir = "/" + streamName +"/" + str(now.year) + "/" + str(now.month) + " - " + str(now.strftime("%b"))
oclocation = ocbasedir+ targetdir + "/"
debug ("INFO: Starting at " + str(now))
debug ("INFO: Will stop at " + str(end))

title = filename.replace(".mp3", "")
artist = streamName
genre = "radio"
album = streamName
debug("INFO: " + stream)
try:
    debug ("INFO: Recording from " + stream + " for " + str(recordatleast))
    #ff = ffmpy3.FFmpeg(inputs={stream: None}, outputs={filename: '-y -acodec copy -t ' + str("recordatleast") + ' -metadata title=' + str(title) + ' -metadata artist=' +  str(artist) + ' -metadata genre=' + str(genre) + ' -metadata album=' + str(album)})
    ff = ffmpy3.FFmpeg(inputs={stream: None}, outputs={
        filename: '-y -acodec copy -t '+ str(recordatleast) +' -metadata title=' + str(filename) + ' -metadata artist=' + str(artist) + ' -metadata genre=' + str(genre) + ' -metadata album=' + str(album) + ' -loglevel quiet'})
    debug ("INFO: Command = " +ff.cmd)
    
    ff.run()
except Exception as e:
    debug ("ERROR: Cannot record from that stream")
    debug ("Error = " + str(e))
    exit (1)


if toOwncloud:
    debug ("INFO: Uploading to OwnCloud")
    try:
        debug ("Making connections ...")
        oc = owncloud.Client(ocurl)
    except:
        debug ("Could not connect to Owncloud")
    try:
        oc.login(ocuser, ocpass)
    except Exception as e:
        debug ("ERROR: Cannot login as + ocuser + " and + ocpass + " at " + ocurl)
    dirs = oclocation.split("/")
    dirtocreate = ""
    for x in dirs:
        dirtocreate = dirtocreate + x + "/"
        try:
            oc.mkdir(dirtocreate)
        except:
            debug ("INFO: Cannot create OwnCloud Dir, possibly because it exists already")

    try:
        oc.put_file(oclocation + filename, filename)
    except Exception as e:
        debug ("Error: "  + e)
        debug ("ERROR: Could not upload file. Go figure ...")
        error=True
if toSSH:
    debug ("INFO: Uploading file to podcast")
    
    #sftp = pysftp.Connection(username=sshuser, private_key=sshkeyfile)
    #sftp.put(filename,sshpath + filename)
    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    if sshkeyfile!="":
        debug ("INFO: Connecting via SSH and keyfile")
        try:
            ssh.connect(sshserver, username=sshuser, password=sshpass, key_filename=sshkeyfile)
            #sftp = pysftp.Connection(host=sshserver ,username=sshuser, private_key=sshkeyfile)
        except Exception as e:
            debug ("ERROR: Could not connect via key_file to " + sshserver + " using key file as user " + sshuser)
            debug ("Error = " + str(e))
            error=True
    else:
        try:
            ssh.connect(sshserver, username=sshuser, password=sshpass)
        except Exception as e:
            debug ("ERROR: Could not connect via password to " + sshserver + " using password as user " + sshuser)
            debug ("Error = " + str(e))
            error=True
    
    sftp = ssh.open_sftp()
    debug("INFO: Will put " + filename + " to " + sshpath+filename)
    sftp.put(filename, sshpath + filename)
    sftp.close()
    ssh.close() 

if toLocal:
    debug ("INFO: Saving to local location")
    if savelocation[-1] =="/":
        savelocation = savelocation[:-1]
    debug ("INFO: Will make dir " + savelocation + targetdir)
    try:
        os.makedirs(savelocation + targetdir)
    except Exception as e:
        debug("ERROR: " + str(e))
        debug ("ERROR: Could not create local dir, possibly because it exists")
    try:
        debug ("INFO: Making local transfer to " + savelocation + targetdir+ "/" +filename)
        shutil.copyfile (filename, savelocation + targetdir+ "/" +filename)
    except Exception as e:
        debug ("ERROR:" + str(e))
        debug ("ERROR: Could not copy file")
        error=True

if toLocalFlat:
    debug ("INFO: Saving to local location (without Folder Structure)")
    if  saveToFlat[-1] =="/":
        saveToFlat = saveToFlat[:-1]
    try:
        debug ("INFO: Making local transfer to " + saveToFlat + "/" +filename)
        shutil.copyfile (filename, saveToFlat + "/" +filename)
    except Exception as e:
        debug ("ERROR:=" + str(e))
        debug ("ERROR: Could not copy file")
        error=True

if toPodcast:
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        debug ("INFO: Will hit " + podcastrefreshurl)
        contents = urllib.request.urlopen(podcastrefreshurl, context=ctx).read()
    except Exception as e:
        debug ("ERROR: There was an error forcing the podcast generator to refresh. Is the URL Correc?")
        debug (str(e))
        error=True
if notify:
    try:
        pushovertoken = getSetting(name.upper(), "pushovertoken")
        pushoverkey = getSetting(name.upper(), "pushoverkey")
    except Exception as e:
        debug ("ERROR: Error reading Pushover Token from Settings file")
    try:
        message = "Recording Completed. Audio file is " + str("{:.2f}".format((os.stat(filename).st_size/(1000000)))) + "MB"    
        conn = http.client.HTTPSConnection("api.pushover.net:443")
        conn.request("POST", "/1/messages.json",
        urllib.parse.urlencode({
            "token": pushovertoken,
            "user": pushoverkey,
            "message": message,
        }), { "Content-type": "application/x-www-form-urlencoded" })
        conn.getresponse()
    except Exception as e:
        debug ("ERROR: Could not send Pushover Notification")
        debug (str(e))

if error:
    debug("ERROR: There have been non terminal errors. Will leave temporaty file in place")
else:
    debug ("INFO: Deleting local files")
    os.remove(filename)
exit(0)



