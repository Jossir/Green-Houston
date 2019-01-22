#This script is executed on a Raspberry Pi which is connected to a 8-way power relay and multiple sensors (temperature, humidity, co2, UV and video feedback (still in development). 
#The power relay is to toggle equipment on/off i.e. Dehumidifier, Co2 regulator, exhaust fan, inside Fans, water pump and air-conditioner. 
#In short the script is an automation bot which efficently maintains a controlled environment.


import RPi.GPIO as GPIO
import time
import datetime
import sys
import Adafruit_DHT
import serial 
import threading
import smtplib
import traceback

from email.MIMEMultipart import MIMEMultipart
from email.MIMEBase import MIMEBase
from email import Encoders
from email.mime.text import MIMEText
from threading import Thread

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

# global settings
# light cycle in pm
lightsOn = 12
lightsOff = 23
Co2 = True
onExhaustTime = 12

# internal variables
hightOutHumidity = False
toggleFanB = False

# Output Relay Channels
relay_wfan = 6  # Ch1
relay_dehumidifier = 13  # Ch2
relay_CO2 = 19  # Ch3
relay_extractorFan = 26  # Ch4

relay_wfanB = False
relay_dehumidifierB = False
relay_CO2B = False
relay_extractorFanB = False

# Relay Output Pin Setup
GPIO.setup(relay_wfan, GPIO.OUT)
GPIO.setup(relay_dehumidifier, GPIO.OUT)
GPIO.setup(relay_CO2, GPIO.OUT)
GPIO.setup(relay_extractorFan, GPIO.OUT)
GPIO.output(relay_wfan, GPIO.LOW)
GPIO.output(relay_dehumidifier, GPIO.LOW)
GPIO.output(relay_CO2, GPIO.LOW)
GPIO.output(relay_extractorFan, GPIO.LOW)

# Sensor Input Pins
sense_Temp_Humid = 4
sense_CO2 = 27
# sens_UV = 22 # Needs I2C

# Sensor Input Pin Setup
# GPIO.setup(4,GPIO.IN, pull_up_down=GPIO.PUD_UP)
# GPIO.setup(17,GPIO.IN, pull_up_down=GPIO.PUD_UP)
# GPIO.setup(27,GPIO.IN, pull_up_down=GPIO.PUD_UP)
# GPIO.setup(22,GPIO.IN, pull_up_down=GPIO.PUD_UP)

# co2 setup
global useCo2
s = None
filename = 'GrowLog.txt'
filenameCSV = 'growLog.csv'

# internal vriables
counter = 0


def extractorOff():
	global relay_extractorFanB
	if relay_extractorFanB:
		GPIO.output(relay_extractorFan, GPIO.LOW) 
		print('Channel 4 off - Extractor Fan')
		relay_extractorFanB = False


def extractorOn():
	global relay_extractorFanB
	if not relay_extractorFanB:
		GPIO.output(relay_extractorFan, GPIO.HIGH)
		print('Channel 4 on - Extractor Fan')
		relay_extractorFanB = True


def co2On():
	global relay_CO2B
	if not relay_CO2B:
		print('Channel 3 on - Co2')
		GPIO.output(relay_CO2, GPIO.HIGH)
		relay_CO2B = True


def co2Off():
	global relay_CO2B
	if relay_CO2B:
		print('Channel 3 off - Co2')
		GPIO.output(relay_CO2, GPIO.LOW)
		relay_CO2B = False


def dehumidifierOn():
	global relay_dehumidifierB
	if not relay_dehumidifierB:
		print('Channel 2 on - dehumidifier')
		GPIO.output(relay_dehumidifier, GPIO.HIGH)
		relay_dehumidifierB = True

def dehumidifierOff():
	global relay_dehumidifierB
	if relay_dehumidifierB:
		print('Channel 2 off - dehumidifier')
		GPIO.output(relay_dehumidifier, GPIO.LOW)
		relay_dehumidifierB = False

def setupCo2():
	global s
	s = serial.Serial('/dev/ttyS0', baudrate=9600, bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, timeout=1.0)


def readCo2Data():
	b = bytearray([0xFF, 0x01, 0x86, 0x00, 0x00, 0x00, 0x00, 0x00, 0x79])
	s.write(b)
	time.sleep(0.5)
	result = s.read(9)
	# return(result)
	try:
		checksum = (0xFF - ((ord(result[1]) + ord(result[2]) + ord(result[3]) + ord(result[4]) + ord(result[5]) + ord(result[6]) + ord(result[7])) % 256)) + 0x01
		if checksum == ord(result[8]):
			co2ReadingTemp = (ord(result[2]) * 256 + ord(result[3]))
			if co2ReadingTemp is None:
				print('Error reading Co2 Nontype - using previous value')
				return -1
			else:
				return co2ReadingTemp
	except:
		print('Error reading Co2 Checksum error - using previous value')

		return -1

def lights():
	timeinHours = time.gmtime().tm_hour + 2
	if(lightsOn > lightsOff):
		if(timeinHours >= lightsOn or timeinHours < lightsOff):
			return True
		else:
			return False
	else:
		if(timeinHours >= lightsOn and timeinHours < lightsOff):
			return True
		else:
			return False



def toggleFan():
	count = 0
	while True:
		if(count == 0):
			GPIO.output(relay_wfan, GPIO.LOW)
			relay_wfanB = False
			count = count + 1
			time.sleep(1)
		else:
			GPIO.output(relay_wfan, GPIO.HIGH)
			relay_wfanB = True
			count = count - 1
			time.sleep(1)

		        	
def vent():
	global relay_extractorFanB
	if(lights()):
		extractorOn()
		print('Exhaust time: ' + str(onExhaustTime) + ' minutes')
		#dehumidifierOff()
		time.sleep(60 * onExhaustTime)
		extractorOff()
	else:					#night time vent
		extractorOn()
		while not lights():
			time.sleep(5)
			
		extractorOff()


def shortVent(ventTime):
	if(relay_CO2B):
		GPIO.output(relay_CO2, GPIO.LOW)
		time.sleep(2)

	extractorOn()
	print('Exhaust time: '+str(ventTime)+' secounds')
	time.sleep(ventTime)
	extractorOff()

	if(relay_CO2B):
		time.sleep(1)
		GPIO.output(relay_CO2, GPIO.HIGH)

def dehumidify(humidity):
	if(lights()):
		if float(humidity) > 55.0 and not relay_dehumidifierB:
			dehumidifierOn()
		elif float(humidity) < 47.0 and relay_dehumidifierB:
			dehumidifierOff()
	else:
		if float(humidity) > 55.0 and not relay_dehumidifierB:
			dehumidifierOn()
		elif float(humidity) < 47.0 and relay_dehumidifierB:
			dehumidifierOff()
	
def fileWrite(humidity, temperature, co2Reading, light):
	# write to file
	now = datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")

	#Print to console

	data = now + ",  Co2: " + str(co2Reading) + ",  " + 'Temp: {0:0.1f} C  Humidity: {1:0.1f} %'.format(temperature, humidity)
	print (data)
	#txt file	
	file_data = open(filename , "a")
	file_data.write(data+ "\n")
	file_data.close()
	#csv file
	data = now + ", " + str(co2Reading) + ", " + '{0:0.1f}, {1:0.1f}'.format(temperature, humidity) + ", " + str(light) + ", " + str(relay_extractorFanB) + ", " + str(relay_CO2B) + ", " + str(relay_dehumidifierB) +"\n"
	file_data = open(filenameCSV , "a")
	file_data.write(data)
	file_data.close()


def sendemail(from_addr, to_addr_list, subject, message, login, password):

	msg = MIMEMultipart() #create message

	# setup the parameters of the message
	msg['From']=from_addr
	msg['To']=to_addr_list
	msg['Subject']=subject

	# add in the message body
       	msg.attach(MIMEText(message, 'plain'))
	
	#add attatchment
	part = MIMEBase('application', "octet-stream")
	part.set_payload(open("growLog.csv", "rb").read())
	Encoders.encode_base64(part)

	part.add_header('Content-Disposition', 'attachment; filename="growLog.csv"')

	msg.attach(part)
	
	# set up the SMTP server
 	server = smtplib.SMTP('smtp.gmail.com', 587)
	server.starttls()
	server.login(login,password)
	problems = server.sendmail(from_addr, to_addr_list, msg.as_string())
	del msg
	# Terminate the SMTP session and close the connection
	server.quit()

def startUp():
	if(Co2):
		print('Co2 Enabled')
	else:
		print('Co2 Disabled')
	if(lights()):
		print('Light status: On')
	else:
		print('Light status: Off')
	
	print('Channel 1 On - Inside Fans')
	GPIO.output(relay_wfan, GPIO.HIGH)
	relay_wfanB = True
	
	co2Off()
	dehumidifierOn()
	#dehumidify()
	Thread(target=vent).start()
	
	#extractorOff()
	#t = 2 + y

 	#sendemail(from_addr = 'JoseSirbagrown@gmail.com', to_addr_list = 'josesirba7@gmail.com', subject = 'GrowLog', message = 'test' , login = 'stankydankhomegrown@gmail.com', password = 'removed password*')
try:
	counter = 0
	startUp()
	
	# timeinHours = time.gmtime().tm_hour+2
	# timeinMinutes = time.gmtime().tm_min
	# print(str(timeinHours))
	setupCo2()
	useCo2 = False
	pauseCheckHum = True
	pauseCheckTemp = True
	humidity, temperature = Adafruit_DHT.read_retry(11, sense_Temp_Humid)

	while True:
		tempL = lights()
		if(tempL and useCo2 == False):
			useCo2 = True;
			print('Lights on - enable Co2 functionality')
			#extractorOff()
			 
 			sendemail(from_addr = 'JoseSirbakhomegrown@gmail.com', to_addr_list = 'josesirba7@gmail.com', subject = 'GrowLog - lights on', message = 'to do' , login = 'stankydankhomegrown@gmail.com', password = 'removed password*')
			print('Daily data mail sent')

			#co2On()
			
		elif(tempL == False and useCo2):
			#send daily email
			counter = 0

 			sendemail(from_addr = 'JoseSirbahomegrown@gmail.com', to_addr_list = 'josesirba7@gmail.com', subject = 'GrowLog - lights off', message = 'to do' , login = 'stankydankhomegrown@gmail.com', password = 'removed password*')
			print('Daily data mail sent')
			useCo2 = False
			
			co2Off()
			if(not relay_extractorFanB):
				print('Lights off - disable Co2 functionality')
				Thread(target=vent).start()
		elif(tempL == False):
			co2Off()

		# Read Temp + Humidity
		newHumidity, newTemperature = Adafruit_DHT.read_retry(11, sense_Temp_Humid)
		
		# Outlier Check - can't check for two outliers in a row
		if pauseCheckTemp:
			pauseCheckTemp = False
			temperature = newTemperature
		elif abs(temperature - newTemperature)<2 and pauseCheckTemp == False:
			temperature = newTemperature
		elif pauseCheckTemp == False:
			pauseCheckTemp = True
			print('Temperature outlier of: ' + str(newTemperature) +'C  - computing on previous value') 
		if pauseCheckHum:
			pauseCheckHum = False
			humidity = newHumidity
		elif abs(humidity - newHumidity)<3 and pauseCheckHum == False:
			humidity = newHumidity
			pauseCheckHum = False
		elif pauseCheckHum == False:
			pauseCheckHum = True
			print('Humidity outlier of: ' + str(newHumidity)+'%  - computing on previous value') 

		#humidity, temperature = Adafruit_DHT.read_retry(11, sense_Temp_Humid)


		if(humidity > 100 or temperature >50):
			humidity = -1
			temperature = -1
			print('Corrupted read data temp & humidity')
         		
		# write to file
		co2ReadingTemp = readCo2Data()
		 
		if co2ReadingTemp is None:
			print('Error reading Co2 Nontype')
			co2ReadingTemp=-1
		try:
			if(co2ReadingTemp<0):
				t = 1
		except:
			print('Error reading Co2 - not number')
			co2ReadingTemp=-1


		#elif(not co2ReadingTemp.isdigit()):
		#	print('Error not digit')
		#	co2ReadingTemp=-1

		#if co2ReadingTemp !=-1:#checking that there are no errors, if so keep previous value
		co2Reading = co2ReadingTemp

		fileWrite(newHumidity, newTemperature, co2Reading, tempL)
		# Add co2
		if(humidity != -1 and co2Reading != -1):
			if tempL:
				if(relay_extractorFanB == False):  # extractor off

					if(relay_CO2B == True):  # Co2 on
						if(float(co2Reading) > 1500.0):
							print('Room full')
							co2Off()
												
					elif float(co2Reading) < 1500.0:
						if((counter > 4 and float(temperature) > 33.0) or counter > 9):
							counter = 0
							Thread(target=vent).start()
						else:	
							print('Turn Co2 on. Counter:' + str(counter))
							co2On()
							counter = counter + 1
					
					#if float(temperature) == 34.0:					

						#Thread(target=shortVent(20)).start()
										
					if float(temperature) > 35.0:
						print('turn on fan too hot')
						if(relay_CO2B):
							co2Off()
							time.sleep(10)

						Thread(target=vent).start()
						counter = 0
					elif float(humidity) > 87.0 and relay_CO2B == False:					

						Thread(target=shortVent(30)).start()

												

					elif float(humidity) > 93.0:
						print('turn on fan too humid')
						if(relay_CO2B):
							co2Off()
							time.sleep(10)
						Thread(target=vent).start()
						counter = 0


			else:#lights off
				extractorOn()
				
				#if not hightOutHumidity:
				#	if relay_dehumidifierB:
				#		if relay_extractorFanB:
				#			if float(temperature) < 18.0 and float(humidity) <= 80.0:
				#				extractorOff()
				#		else:
				#			if float(temperature) > 18.0 or float(humidity) > 80.0 or float(co2Reading)>650:
				#				extractorOn()
				#				
				#	else:
				#		extractorOn()
				#else:#more humid outside then inside
				#	if relay_dehumidifierB:
				#		
				#		if float(co2Reading)<610:
				#			extractorOff()
				#		elif float(co2Reading)>700:
				#			extractorOn()		
				#	else:
				#		extractorOn()


		#Dehumidifier
		if(humidity != -1):
			dehumidify(humidity)
		time.sleep(9)


except KeyboardInterrupt:         
	GPIO.cleanup()
#except Exception as detail:
except Exception:
	t = traceback.format_exc()
	print('Error in code: '+ t +' - email sent')
	sendemail(from_addr = 'stankydankhomegrown@gmail.com', to_addr_list = 'josesirba7@gmail.com', subject = 'WARNING - growRoomAI.py crashed', message = t , login = 'stankydankhomegrown@gmail.com', password = 'Logmein0919')
	#exec('growRoomAI.py')		
