#!/opt/splunk/bin/python
#Need to use Splunk's shipped python and not your system local python install
##########################################################################################################################################
# Date:		Dec 27, 2015. Splunk Community License
# Script:	getimage.py v1.9
# Auther:	Mohamad Hasssan, Splunk SE NC
#
# Inputs:	<image_file_fieldname>  <remote_server_url_where_image_is_hosted>
# Outputs:	Interact with search pipeline and inject serveral output fields: 
#		[rc_wget]:	The output of wget command
#		[rc_convert]:	The output of ImageMagick convert command
#		[new_image] : 	The converted image name
#		[file_loc ]:	*experimental* location new image (using file:///)
#		[link]:		The URL of the new converted image
#		[cached_imaged]:Boolean if images was served from local cache rather than retrieved
#		[wget_result]:	More cleaned up wget output
#		[app_shortcut_url]: location of all cached images

# Usage:	sourcetype=mysourcetype | getimage image_file http://10.211.55.3/icons
#
# Description:  This custom command is created to solve a specific use-case where the user needed a mechanism 
#		to retrieve images (from an image server) and display them in a dashboard. The script has the 
#		ability to convert the images types before presenting to users (ex: images are in tiff format 
#		where most browser don't know how to display). The script will utilize a cache directory 
#		for retrieved images.You can control the age if caches images 
#		to reduce the stress on the network. The script assumes the existing of [image_file] field in 
#		raw data where the name of the image file is stored
#
# Todo:		Reimplement wget and convert function using python libaraies. Which requires PIL and wget modules
#
##########################################################################################################################################

import sys,splunk.Intersplunk
import logging
from sys import argv
from sys import stdout
import os
import time
import string
import subprocess
#from html import XML
#import urllib2
import socket
#import wget
import ConfigParser
import shutil
from stat import *
#import datetime

CONFIG="/opt/splunk/etc/apps/rx_image_review_app/bin/getimage.conf"
splunkhost=(socket.gethostname())
splunkhost="localhost"    #for testing

#------------------------------- shell_cmd() -------------------------
def shell_cmd(cmd):
        line=0
        p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        for line in p.stdout.readlines():
                line,
        retval = p.wait()
        logger.debug("EXIT shell_cmd: cmd=[%s]  rc=[%s]" , cmd, line )
        return (line)
#------------------------------- shell_cmd() -------------------------
#------------------------------- SyncImgTimes()-------------------------
#sync timestamps, otherwise caching logic will break
def SyncImgTimes (oldimg,newimg):
	st = os.stat(newimg)
	newimg_atime = st[ST_ATIME] #access time
	newimg_mtime = st[ST_MTIME] #modification time
	os.utime (oldimg, (newimg_atime, newimg_mtime) )
	#logger.debug ("[%s]: atime: %s" , oldimg, newimg_atime)
	logger.debug ("Sync Images [%s %s] time [%s]"  , oldimg, newimg, newimg_mtime)
	return
#------------------------------- SyncImgTimes()-------------------------
#------------------------------- ConfigSectionMap() -------------------------------
#https://wiki.python.org/moin/ConfigParserExamples
def ConfigSectionMap(section):
    dict1 = {}
    options = Config.options(section)
    for option in options:
        try:
            dict1[option] = Config.get(section, option)
            if dict1[option] == -1:
                DebugPrint("skip: %s" % option)
        except:
            print("exception on %s!" % option)
            dict1[option] = None
    return dict1
#------------------------------- ConfigSectionMap() -------------------------------

#------------------------------- LOGGING SETUP ------------------------------------
#DEBUGING, Disable in production! Make sure first argv is __GETINFO__  or __EXECUTE__
#(isgetinfo, sys.argv) = splunk.Intersplunk.isGetInfo(sys.argv)
logger = logging.getLogger("getimage.py")
logger.setLevel(logging.DEBUG)
logfile = logging.StreamHandler(open("/opt/splunk/var/log/splunk/getimage.log", "a"))
logfile.setLevel(logging.DEBUG)
logfile.setFormatter(logging.Formatter('%(asctime)s [%(process)06d] %(levelname)-6s %(name)s: %(message)s'))
logger.addHandler(logfile)
#------------------------------- LOGGING SETUP ------------------------------------

#------------------------------- CONFIGS ------------------------------------
#Get configuration file
try:
	f = open(CONFIG)
	f.close()
except IOError as e:
	logger.debug("ERROR: Config file is missing or unreadable! [%s]", CONFIG)
	splunk.Intersplunk.parseError("ERROR: Config file is missing or unreadable!")
	
Config = ConfigParser.ConfigParser()
Config.read(CONFIG)
Config.sections()
CACHE_AGE = float(ConfigSectionMap("image")['cache'])
NEWIMGEXT = ConfigSectionMap("image")['newimgext']
OLDIMGEXT = ConfigSectionMap("image")['oldimgext']
IMGNOTFOUND = ConfigSectionMap("image")['imgnotfound']
IMGERROR = ConfigSectionMap("image")['imgerror']
NEWSIZE = ConfigSectionMap("image")['newsize']
WGETCMD = ConfigSectionMap("commands")['wgetcmd']
CONVERTCMD = ConfigSectionMap("commands")['convertcmd']
APP_STATIC_PATH = ConfigSectionMap("paths")['app_static_path']
APP_SHORTCUT_URL = ConfigSectionMap("paths")['app_shortcut_url']
EXPOSED_HTTP_PATH = ConfigSectionMap("paths")['exposed_http_path']
#------------------------------- CONFIGS ------------------------------------

logger.debug("------ Starting script -------------")

if not os.path.exists(EXPOSED_HTTP_PATH):
	os.makedirs(EXPOSED_HTTP_PATH)
if not os.path.exists(APP_STATIC_PATH):
	        os.makedirs(APP_STATIC_PATH)

if len(sys.argv) < 2:
	    splunk.Intersplunk.parseError("No arguments provided")

if len(sys.argv) != 3:
	print "Usage: getimage <raw_image_fieldname> <http://<hostname>/path/>"
    	sys.exit()

args, kwargs = splunk.Intersplunk.getKeywordsAndOptions()
logger.debug("Args: %r, key/value settings: %r", args, kwargs)

remote_server_image_url = str(sys.argv[2])
raw_image_fieldname = str(sys.argv[1])


#DEBUG: outputInfo automatically calls sys.exit(). Disable in production
#if isgetinfo:
#   splunk.Intersplunk.outputInfo(False, False, True, False, None, True)

#splunk.Intersplunk.readResults(input_buf, settings, has_header)
results = []
results = splunk.Intersplunk.readResults(None, None, True)

#DEBUG: Fetch results being passed to this search command
#results,dummyresults,settings = splunk.Intersplunk.getOrganizedResults()
#logger.debug("Settings passed:  %r", settings)

#------------------------------ CACHING -----------------------------------------
#Clear cached images (files) if older than image_cache_age
try:
	now= time.time()
	for f in os.listdir(EXPOSED_HTTP_PATH):
		f = os.path.join(EXPOSED_HTTP_PATH, f)
		if os.stat(f).st_mtime < (now - CACHE_AGE):
  			if os.path.isfile(f):
   				os.remove(f)	
				#logger.debug("[%s] DELETED! ", f)

except:
        import traceback
        stack =  traceback.format_exc()
        results = splunk.Intersplunk.generateErrorResults("Error : Traceback: " + str(stack))()
#------------------------------ CACHING -----------------------------------------

#Copy static images used to communicate condition into visiable directory incase cache directory deleted
shutil.copy2 (APP_STATIC_PATH+IMGNOTFOUND, EXPOSED_HTTP_PATH)
shutil.copy2 (APP_STATIC_PATH+IMGERROR, EXPOSED_HTTP_PATH)

#----------------- main() ---------------------------------------------
try:
	for r in results:
        	if raw_image_fieldname in r:
			r['rc_wget']= []
			r['rc_convert']= []
			oldimg = r[raw_image_fieldname]
			split_img = r[raw_image_fieldname].split('.')  # parse
			img = split_img[0]			#remove extention
			newimg = img + '.' + NEWIMGEXT
			logger.debug("------ Start processing new image:-------------")

			#r['new_image'] = "http://%s:8000%s%s" % (splunkhost,EXPOSED_HTTP_PATH,newimg)
			#r['new_image'] = "%s%s" % (EXPOSED_HTTP_PATH,newimg)
			r['new_image'] = "%s" % (newimg)
			r['file_loc'] = "file://%s%s" % (EXPOSED_HTTP_PATH,newimg)
			r['link'] = "http://localhost:8000/%s%s" % (APP_SHORTCUT_URL,newimg)
			
			#-------------------------------------------------------------------------------------------
			#Caching is determined based on oldimg only
			if (os.path.isfile(EXPOSED_HTTP_PATH+oldimg) and os.access(EXPOSED_HTTP_PATH+oldimg, os.R_OK)):
			    r['cached_image'] = "Y"
			    rc_wget = ""
			    cached = r['cached_image']	
			    r['image_size']= os.path.getsize(EXPOSED_HTTP_PATH + oldimg)
			    logger.debug("Image is ##cached##! name:[%s] size:[%s]" ,oldimg, r['image_size']) 

			else: 
			    rc_wget=shell_cmd(WGETCMD + ' ' + remote_server_image_url + oldimg + ' -O ' + EXPOSED_HTTP_PATH + oldimg + ' -nv ')
			    r['rc_wget']=rc_wget
			    r['cached_image'] = "N"
			    cached = r['cached_image']
			    logger.debug("Image NOT cached!  name[%s].", oldimg ) 
			#-------------------------------------------------------------------------------------------

			#-------------------------------------------------------------------------------------------
			#find() returns -1 when substring is not found (!=-1 found   ==-1 NOT found)
			#check for 2 possible error conditions
			if (rc_wget.find("failed") != -1):   	#connection refused
				 os.remove(EXPOSED_HTTP_PATH+oldimg) 	#clean after wget for failed dloads
				 annotate = ' -fill black -box \"#C0C0C0\"  -gravity south -annotate 0  \"'+remote_server_image_url+'\"' + ' '
				 rc_convert= shell_cmd(CONVERTCMD + ' ' + EXPOSED_HTTP_PATH + IMGERROR + annotate +\
							EXPOSED_HTTP_PATH + IMGERROR)
				 r['rc_convert']="convert was not called"
				 r['wget_result']= (rc_wget.split('failed:'))[1]
				 r['new_image'] = "%s" % (IMGERROR)
			    	 r['cached_image'] = ""
				 cached = r['cached_image']
				 r['link'] = "ERROR CONNECTION TO IMAGE SERVER http://localhost:8000" 
				 logger.debug("ERROR: Connection refused. Created img_error icon. name:[%s] new_image:[%s]" , oldimg,r['new_image']) 
				    
			elif (rc_wget.find("ERROR") != -1):   	#404 or 403 errors
				 os.remove(EXPOSED_HTTP_PATH+oldimg) 	#clean after wget for failed dloads
				#handle browser caching same IMGNOTFOUND (impacting annotation) 
				 r['wget_result']= (rc_wget.split('ERROR'))[1]
				 annotate = ' -fill black -box \"#C0C0C0\"  -gravity south -annotate 0  \"'+r['wget_result']+remote_server_image_url+oldimg+'\"' + ' '
				 rc_convert= shell_cmd(CONVERTCMD + ' ' + EXPOSED_HTTP_PATH + IMGNOTFOUND + annotate +\
							EXPOSED_HTTP_PATH + oldimg+IMGNOTFOUND)
				 r['rc_convert']="convert was not called"
		        	 r['rc_wget']= rc_wget
				 r['new_image'] = "%s" % (oldimg+IMGNOTFOUND)
				 r['link'] = "http://localhost:8000/%s%s" % (APP_SHORTCUT_URL,IMGNOTFOUND)
				 logger.debug("ERROR: 404 File not found. Created not_found icon. name:[%s] new_image:[%s]" , oldimg,r['new_image']) 

			else: #Life is good!
				 cached = r['cached_image']	
		        	 r['rc_wget']= rc_wget
				 r['wget_result']= "Ok"

				 if cached == 'Y' :
					 annotate = ' -fill yellow -box \"#00770080\"  -gravity south -annotate 0  \"' + newimg + '    ##CACHE##'+  '\" '   
					 rc_convert= shell_cmd(CONVERTCMD + ' ' + EXPOSED_HTTP_PATH + oldimg + ' -resize ' + \
							 	NEWSIZE + annotate + EXPOSED_HTTP_PATH + newimg)
				 	 #SyncImgTimes (EXPOSED_HTTP_PATH+oldimg, EXPOSED_HTTP_PATH+newimg)
				 	 logger.debug("Life is good! Created #cache# annotation. name:[%s] cached:[%s]" , oldimg,cached) 
			         else:
					 annotate = ' -fill yellow -box \"#00770080\"  -gravity south -annotate 0  "'  + newimg + '" '  
				 	 rc_convert= shell_cmd(CONVERTCMD + ' ' + EXPOSED_HTTP_PATH + oldimg + ' -resize ' + \
								NEWSIZE +  annotate  + EXPOSED_HTTP_PATH + newimg)
				 	 SyncImgTimes (EXPOSED_HTTP_PATH+oldimg, EXPOSED_HTTP_PATH+newimg)
				 	 logger.debug("INFO: Life is good! Created annotation. name:[%s] cached:[%s]" , oldimg,cached) 

			r['rc_convert']=rc_convert
			r['app_shortcut_url'] = "%s" % (APP_SHORTCUT_URL)

			#testing stuff  3/1/16
			#r['cache_age'] = "%s" % (CACHE_AGE)
			#timestamp = (now - CACHE_AGE)
			#value = datetime.datetime.fromtimestamp(timestamp)
			#print(value.strftime('%Y-%m-%d %H:%M:%S'))
			#r['cache_expire'] = "%s" % (value.strftime('%Y-%m-%d %H:%M:%S'))
			#if os.stat(f).st_mtime < (now - CACHE_AGE):
			logger.debug("------ Finished processing new image:-------------\n")
			#r['new_image'] = "http://%s:8000%s%s" % (splunkhost,EXPOSED_HTTP_PATH, IMGNOTFOUND)
			#-------------------------------------------------------------------------------------------
		

			    #filename = wget.download(remote_server_image_url + oldimg,EXPOSED_HTTP_PATH + oldimg,0)
		#logger.debug("------- rc:[%s] find[%d] newimage:[%s]  cached:[%s] --------", rc, rc.find("ERROR"),newimg,r['cached_image'])


except:
   	import traceback
    	stack =  traceback.format_exc()
    	results = splunk.Intersplunk.generateErrorResults("Error : Traceback: " + str(stack))
#----------------- main() ---------------------------------------------


#Output of script is expected to be pure CSV
splunk.Intersplunk.outputResults(results)


#Incase we want to launch local browser!
#esubprocess.call(['/Applications/Firefox.app/Contents/MacOS/firefox', EXPOSED_HTTP_PATH])
#subprocess.call(['/Applications/Safari.app/Contents/MacOS/Safari', newimg])

#Cleanup. Breaks script 12/25/15
#os.remove(EXPOSED_HTTP_PATH + oldimg)
#os.remove(EXPOSED_HTTP_PATH + newimg)



