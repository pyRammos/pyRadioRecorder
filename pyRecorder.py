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
import ssl
import logging

def getSetting(section, setting):
    config = configparser.ConfigParser()
    try:
        config.read('settings.cfg')
    except Exception as e:
        debug("Cannot read settings.cfg")
    #section = "DEFAULT"
    try:
        #print ("Setting " + setting + " to " + config[section][setting])
        return config[section][setting]
    except:
        print ("Key " + setting + " not found in section "+ section + ".")

def debug(message):
    print (str(datetime.datetime.now()) + " --::-- " + str(message))
    logging.debug(str(message))

name = ""
duration = -1
toOwncloud = False
toPodcast = False
toLocal = False
toSSH = False

logging.basicConfig(filename= "recorder.txt", level=logging.DEBUG,format="%(asctime)s %(message)s")
debug ("============ New Start ============")


if len (sys.argv) <2:
    debug  ("You have not passed enough arguments")
    debug ("Usage: pyRecord name=NAME duration=DURATION_IN_SECONDS [toOwncloud] [toPodcast] [toLocal] [toSSH]")

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
            debug ("Usage: pyRecord [name=NAME] duration=DURATION_IN_SECONDS [toOwncloud] [toPodcast] [toLocal] [toSSH]")
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
    if "toSSH" in str(param).lower():
        #print("Will upload via SSH")
        toSSH = True

if name=="":
    debug ("You must specify a name, e.g. name=myShow")
    debug ("Usage: pyRecord [name=NAME] duration=DURATION_IN_SECONDS [toOwncloud] [toPodcast] [toLocal] [toSSH]")
    exit(1)

if duration <=0 :
    debug ("I do need the duration of the clip you want me to record. Don't make me guess ...")
    debug ("Usage: pyRecord name=NAME duration=DURATION_IN_SECONDS [toOwncloud] [toPodcast] [toLocal] [toSSH]")
    exit (1)

if toPodcast:
    if  not (toLocal or toSSH):
        debug ("You want to upload this to a podcas generator, but have not set toLocal or toSSH")
        debug ("Usage: pyRecord name=NAME duration=DURATION_IN_SECONDS [toOwncloud] [toPodcast] [toLocal] [toSSH]")
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

stream = getSetting(name.upper(),"stream")
if stream=="" or stream==None:
    debug ("Cannot determine stream url. Set the stream parameter in the settings file. Goodbye")
    exit (1)
if toOwncloud:
    ocuser = getSetting(name.upper(), "ocuser")
    ocpass = getSetting(name.upper(), "ocpass")
    ocurl = getSetting(name.upper(), "ocurl")
    ocbasedir = getSetting(name.upper(), "ocbasedir")
    if ocuser == "" or ocpass=="" or ocurl == "":
        debug ("You want to upload to owncloud but owncloud settings in the config file are incomplete")
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
        debug ("You want to upload to podcast generator but settings in the config file are incomplete")
        debug ("Set the user, password (or key file), server, podcastpath and podcastrefreshurl key/values")
        debug ("Good bye")
if toLocal:
    savelocation = getSetting(name.upper(), "saveto")
    if savelocation=="":
        debug ("You want to save the file to local/mounted filesystems but settings in the config file are incomplete")
        debug ("Please set the savelocation key/value under the "+name+" section")
        debug ("Good bye")
        exit (1)
        debug ("Will save to " + str(savelocation))

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
debug ("Starting at " + str(now))
debug ("Will stop at " + str(end))

title = filename.replace(".mp3", "")
artist = streamName
genre = "radio"
album = streamName
debug(stream)
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
    try:
        oc.login(ocuser, ocpass)
    except Exception as e:
        debug ("Cannot login as + ocuser + " and + ocpass + " at " + ocurl)
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

if toSSH:
    debug ("Uploading file to podcast")
    
    #sftp = pysftp.Connection(username=sshuser, private_key=sshkeyfile)
    #sftp.put(filename,sshpath + filename)
    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    if sshkeyfile!="":
        debug ("Connecting via SSH and keyfile")
        try:
            ssh.connect(sshserver, username=sshuser, password=sshpass, key_filename=sshkeyfile)
            #sftp = pysftp.Connection(host=sshserver ,username=sshuser, private_key=sshkeyfile)
        except Exception as e:
            debug ("Could not connect via key_file to " + sshserver + " using key file as user " + sshuser)
            debug ("Error = " + str(e))
            exit(1)
    else:
        try:
            ssh.connect(sshserver, username=sshuser, password=sshpass)
        except Exception as e:
            debug ("Could not connect via password to " + sshserver + " using password as user " + sshuser)
            debug ("Error = " + str(e))
            exit(1)
    
    sftp = ssh.open_sftp()
    debug("Will put " + filename + " to " + sshpath+filename)
    sftp.put(filename, sshpath + filename)
    sftp.close()
    ssh.close() 

if toLocal:
    debug ("Saving to local location")
    if savelocation[-1] =="/":
        savelocation = savelocation[:-1]
    debug ("will make dir " + savelocation + targetdir)
    try:
        os.makedirs(savelocation + targetdir)
    except Exception as e:
        debug("Error: " + str(e))
        debug ("Could not create local dir, possibly because it exists")
    try:
        debug ("Making local transfet to" + savelocation + targetdir+ "/" +filename)
        shutil.copyfile (filename, savelocation + targetdir+ "/" +filename)
    except Exception as e:
        debug ("Error =" + str(e))
        debug ("Could not copy file")

if toPodcast:
    debug ("Waiting 40 seconds (for mtime compatibility) and refreshing Podcasts by hitting "+ podcastrefreshurl)
    sleep(40)
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        contents = urllib.request.urlopen(podcastrefreshurl, context=ctx).read()
    except Exception as e:
        debug ("There was an error forcing the podcast generator to refresh. Is the URL Correc?")
        debug (str(e))
   
debug ("Deleting local files")

os.remove(filename)


exit(0)



