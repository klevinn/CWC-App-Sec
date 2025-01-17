"""
This python file contains all the functions that does NOT requires the import of the
flask web application's app variable from app.py or current_app from flask library.

This is to allow this file to be run as a standalone script.
"""
# import python standard libraries
import requests as req, uuid, re, json, pathlib
from six import ensure_binary
from typing import Union, Optional
from binascii import Error as BinasciiError
from base64 import urlsafe_b64encode, urlsafe_b64decode
from time import sleep
from hashlib import sha1
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from io import IOBase, BytesIO
from secrets import token_bytes, token_hex, token_urlsafe
from inspect import stack, getframeinfo
from os import environ
from pathlib import Path

# import local python libraries
if (__name__ == "__main__"):
    from sys import path as sys_path
    sys_path.append(str(pathlib.Path(__file__).parent.parent.parent.absolute()))
    from python_files.classes.Constants import CONSTANTS, SECRET_CONSTANTS
    from python_files.classes.Errors import *
elif (__package__ is None or __package__ == ""):
    from classes.Constants import CONSTANTS, SECRET_CONSTANTS
    from classes.Errors import *
else:
    from python_files.classes.Constants import CONSTANTS, SECRET_CONSTANTS
    from python_files.classes.Errors import *

# import third party libraries
import PIL, pymysql
from PIL import Image as PillowImage
from dicebear import DAvatar, DStyle

# import Flask libraries
from flask import url_for, flash, Markup

# For Google Cloud API Errors (Third-party libraries)
import google.api_core.exceptions as GoogleErrors
from google.resumable_media.common import DataCorruption as UploadDataCorruption, InvalidResponse

# for google OAuth2 login
from google_auth_oauthlib.flow import Flow

# For Google Gmail API (Third-party libraries)
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build, Resource

# For Google Cloud KMS (key management service) API (Third-party libraries)
from google_crc32c import Checksum as g_crc32c
from google.cloud import kms
from google.cloud.kms_v1.types import resources

# For Google Cloud reCAPTCHA API (Third-party libraries)
from google.cloud import recaptchaenterprise_v1
from google.cloud.recaptchaenterprise_v1 import Assessment

def decode_and_decrypt_token(tokenInput:str) ->Union[str, None]:
    """
    Decodes the URL-safe base64 encoded token and decrypts it using the token-key in GCP KMS.

    Args:
    - tokenInput (str): The token to decode and decrypt.

    Returns:
    - The decrypted token (str) if successful, None if not.
    """
    try:
        token = symmetric_decrypt(
            ciphertext=urlsafe_b64decode(tokenInput),
            keyID=CONSTANTS.TOKEN_ENCRYPTION_KEY_ID
        )

        # if the token is not equal to 240 characters,
        # return None because it is not a valid token
        return token if (len(token) == 240) else None
    except (DecryptionError, BinasciiError, ValueError, TypeError):
        # If the user tampers with the token in the url
        return None
    except (Exception) as e:
        write_log_entry(
            logMessage=f"Error caught when decoding and decrypting reset password token: {e}",
            severity="NOTICE"
        )
        return None

def get_pagination_arr(pageNum:int=1, maxPage:int=1) -> tuple:
    """
    Returns a tuple of pagination button integers.

    E.g.
    - current page is 5, max pages is 10, then the tuple will be:
    (3, 4, 5, 6, 7)

    - Current page is 1, max pages is 10, then the tuple will be:
    (1, 2, 3, 4, 5)

    - Current page is 10, max pages is 10, then the tuple will be:
    (6, 7, 8, 9, 10)

    - Current page is 1, max pages is 2, then the tuple will be:
    (1, 2)

    Args:
    - pageNum (int): The current page number
    - maxPages (int): The maximum number of pages

    Returns:
    - tuple: A tuple of pagination button integers
    """
    if (pageNum > maxPage):
        pageNum = maxPage

    if (maxPage < 6):
        # if the max pages is less than 6,
        # e.g. if the max pages is 2,
        # then the array will be: (1, 2)
        return tuple(range(1, maxPage+1))

    if (pageNum < 4):
        # if the user's current page number is less than 4, (i.e. 1-3)
        # then the array will be: (1, 2, 3, 4, 5)
        return (1, 2, 3, 4, 5)

    # calculating the difference from the user's current page to max number of pages
    currentFromMax = maxPage - pageNum
    if (currentFromMax <= 2):
        # if the difference is 2 or less
        # e.g. max page is 10, current page is 8,
        # then the array will be: (6, 7, 8, 9, 10)
        return tuple(range(maxPage-4, maxPage+1))
    else:
        # if the difference is more than 2
        # e.g. max page is 10, current page is 7,
        # then the array will be: (5, 6, 7, 8, 9)
        return tuple(range(pageNum-2, pageNum+3))

def upload_from_stream(
    bucketName:Optional[str]=CONSTANTS.PUBLIC_BUCKET_NAME,
    fileObj:IOBase=None,
    uploadDestination:str="",
    cacheControl:Optional[str]=CONSTANTS.DEFAULT_CACHE_CONTROL
):
    """
    Uploads bytes from a stream or other file-like object to Google Cloud Platform Storage API.

    Args:
    - bucketName (str, Optional): Name of the bucket.
        - Default: PUBLIC_BUCKET_NAME defined in Constants.py
    - fileObj (IOBase): A file-like object to upload.
    - uploadDestination (str): Path to the destination in the bucket to upload to.
        - E.g. "user-profiles/file.png" to upload to the user's profile folder in the bucket
        - E.g. "file.png" to upload to the root of the bucket
    - cacheControl (str, Optional): The cache control header to set on the uploaded file.
        - E.g. "public, max-age=60" for a 1 minute cache
        - Default: DEFAULT_CACHE_CONTROL defined in Constants.py

    Raises:
    - UploadFailedError: If the upload fails.
        - Happens if the file is corrupted.

    Returns:
    - str: The public URL of the uploaded file.
    """
    bucket = SECRET_CONSTANTS.GOOGLE_STORAGE_CLIENT.bucket(bucketName)

    blob = bucket.blob(uploadDestination)
    try:
        blob.upload_from_file(fileObj, checksum="crc32c", rewind=True)

        blob.reload()
        blob.cache_control = cacheControl
        blob.patch()
    except (UploadDataCorruption):
        write_log_entry(
            logMessage="UploadDataCorruption: The data uploaded to Google Cloud Storage is corrupted.",
            severity="INFO"
        )
        raise UploadFailedError("Data corruption detected!")
    except (InvalidResponse):
        raise UploadFailedError("Invalid response from Google Cloud Storage!")

    return "/".join(["https://storage.googleapis.com", bucketName, uploadDestination])

def get_blob_path(url:str="") -> str:
    """
    Get the blob path from the Google Storage API URL.

    Args:
    - url (str): The URL of the blob.
        - E.g. https://storage.cloud.google.com/coursefinity-videos/videos/watame.mp4
            - Will return "videos/watame.mp4"

    Returns:
    - The blob path (str): will return the blob path or an empty string if the url is not a valid Google Storage URL.
    """
    # "/" must be in the url as there must be 
    # a bucket name and a blob path in the URL.
    # E.g. <bucket>/<blob> as the url path
    if ("/" not in url):
        return ""

    # Check if the url matches the Google Storage API URL pattern.
    matchedRegex = re.fullmatch(CONSTANTS.GOOGLE_STORAGE_URL_REGEX, url)
    if (matchedRegex is None):
        return ""

    # Return the blob path.
    try:
        blobPath = matchedRegex.group(4)
        return blobPath if (blobPath is not None) else ""
    except (IndexError):
        return ""

def delete_blob(url:str="") -> None:
    """
    Deletes a file from Google Cloud Platform Storage API.

    Args:
    - url (str): The URL of the file/blob to delete from.
        - E.g. "https://storage.googleapis.com/coursefinity/example.webp"

    Raises:
    - FileNotFoundError: If the file to delete does not exist in the bucket.
    - ValueError: If the url is not a valid Google Storage URL.
    """
    blobPath = get_blob_path(url)
    if (blobPath == ""):
        # If the url is not a valid Google Cloud Storage URL
        raise ValueError("File not found!")

    bucketName, blobPath = blobPath.split(sep="/", maxsplit=1)
    bucket = SECRET_CONSTANTS.GOOGLE_STORAGE_CLIENT.bucket(bucketName)
    blob = bucket.blob(blobPath)
    try:
        blob.delete()
    except (GoogleErrors.NotFound):
        raise FileNotFoundError("File not found!")

def get_mysql_connection(
    debug:bool=CONSTANTS.DEBUG_MODE,
    database:Optional[str]=CONSTANTS.DATABASE_NAME,
    user:Optional[str]="coursefinity"
) -> pymysql.connections.Connection:
    """
    Get a MySQL connection to the coursefinity database.

    Args:
    - debug (bool): whether to connect to the MySQL database locally or to Google CLoud SQL Server
        - Defaults to DEBUG_MODE defined in Constants.py
    - database (str, optional): the name of the database to connect to
        - Defaults to DATABASE_NAME defined in Constants.py if not defined
        - Define database to None if you do not want to connect to a database
    - user (str, optional): the name of the user to connect as
        - Defaults to "coursefinity"

    Returns:
    - A MySQL connection.
    """
    password = ""
    if (debug and user == "root"):
        password = environ.get("LOCAL_SQL_PASS")
    elif (not debug and user == "root"):
        password = SECRET_CONSTANTS.get_secret_payload(secretID="sql-root-password")
    elif (user == "coursefinity"):
        password = SECRET_CONSTANTS.get_secret_payload(secretID="sql-coursefinity-password")
    else: # if the user parameter is not "root" or "coursefinity"
        user = "coursefinity" # defaults to coursefinity MySQL account instead
        password = SECRET_CONSTANTS.get_secret_payload(secretID="sql-coursefinity-password")

    if (debug):
        LOCAL_SQL_CONFIG = {"host": "localhost", "user": user, "password": password}
        if (database is not None):
            LOCAL_SQL_CONFIG["database"] = database
        connection = pymysql.connect(**LOCAL_SQL_CONFIG)
    else:
        connection: pymysql.connections.Connection = SECRET_CONSTANTS.SQL_CLIENT.connect(
            instance_connection_string=CONSTANTS.SQL_INSTANCE_LOCATION,
            driver="pymysql",
            user=user,
            password=password,
            database=database
        )
    return connection

def get_dicebear_image(username:str) -> str:
    """
    Returns a random dicebear image from the database

    Args:
        - username: The username of the user
    """
    av = DAvatar(
        style=DStyle.initials,
        seed=username,
        options=CONSTANTS.DICEBEAR_OPTIONS
    )
    return av.url_svg

def send_change_password_alert_email(email:str="") -> None:
    """
    Send an email to the user to alert them that
    their password has been compromised and should be changed.

    Then flashes a message to change their password.

    Args:
    - email (str): The email of the user.
    """
    htmlBody = (
        f"Your CourseFinity account, {email}, password has been found to be compromised in a data breach!",
        f"Please change your password immediately by clicking the link below.<br>Change password:<br>{CONSTANTS.CUSTOM_DOMAIN}{url_for('userBP.updatePassword')}"
    )
    send_email(to=email, subject="Security Alert", body="<br><br>".join(htmlBody))
    flash(
        Markup(f"Your password has been compromised in a data breach, please <a href='{url_for('userBP.updatePassword')}'>change your password</a> immediately!"),
        "Security Alert!"
    )

def accepted_file_extension(filename:Union[str, pathlib.Path]=None, typeOfFile:str="image") -> bool:
    """
    Checks if the file extension is accepted according to the
    tuple of accepted file extensions defined in Constants.py.

    Args:
    - filename (str|pathlib.Path): The filename to check.
    - typeOfFile (str, optional): The type of file to check.
        - Defaults to "image"
        - Accepted values: "image", "video"

    Returns:
    - True if the image extension is accepted, False otherwise.
    """
    if (filename is None):
        raise ValueError("filename cannot be None!")

    fileExtension = ""
    if (isinstance(filename, str)):
        if ("." not in filename):
            return False
        fileExtension = "." + filename.rsplit(".", 1)[1].lower()
    elif (isinstance(filename, pathlib.Path)):
        fileExtension = filename.suffix
    else:
        raise ValueError("filename must be a string or a pathlib.Path object!")

    if (typeOfFile == "image"):
        return (fileExtension in CONSTANTS.ALLOWED_IMAGE_EXTENSIONS)
    elif (typeOfFile == "video"):
        return (fileExtension in CONSTANTS.ALLOWED_VIDEO_EXTENSIONS)
    else:
        raise ValueError("typeOfFile must be either 'image' or 'video'...")

def get_google_flow() -> Flow:
    """
    Returns the Google OAuth2 flow.

    Scopes details:
    - https://developers.google.com/identity/protocols/oauth2/scopes
    """
    flow = Flow.from_client_config(
        SECRET_CONSTANTS.GOOGLE_CREDENTIALS,
        [
            # for retrieving the user's public personal information
            "https://www.googleapis.com/auth/userinfo.profile",
            # for getting the user's email
            "https://www.googleapis.com/auth/userinfo.email",
            # for associating the user with their personal info on Google
            "openid",
            # for Google to send security alerts to the user's email
            "https://www.googleapis.com/auth/gmail.send",
            # for Google to read the user's emails as required for some OAuth2 logins
            "https://www.googleapis.com/auth/gmail.readonly",
        ]
    )
    flow.redirect_uri = CONSTANTS.CUSTOM_DOMAIN + url_for("guestBP.loginCallback")
    return flow

def create_assessment(siteKey:str=CONSTANTS.COURSEFINITY_SITE_KEY, recaptchaToken:str="", recaptchaAction:Optional[str] = None) -> Assessment:
    """
    Creates an assessment in Google Cloud reCAPTCHA API.

    Args:
    - siteKey (str): The site key of the reCAPTCHA site.
        - Defaults to COURSEFINITY_SITE_KEY defined in Constants.py
    - recaptchaToken: The token that is sent to the Google Cloud reCAPTCHA API.
    - recaptchaAction: The action name that is expected to be performed by the user.

    Returns:
    - An Assessment object.
    """
    event = recaptchaenterprise_v1.Event()
    event.site_key = siteKey
    event.token = recaptchaToken
    if (recaptchaAction is not None):
        event.expected_action = recaptchaAction

    assessment = recaptchaenterprise_v1.Assessment()
    assessment.event = event

    projectName = f"projects/{CONSTANTS.GOOGLE_PROJECT_ID}"

    # construct the assessment request
    request = recaptchaenterprise_v1.CreateAssessmentRequest()
    request.parent = projectName
    request.assessment = assessment

    # send to Google reCAPTCHA API
    response = SECRET_CONSTANTS.RECAPTCHA_CLIENT.create_assessment(request)
    # check if the response is valid
    if (not response.token_properties.valid):
        print("invalid due to", response.token_properties.invalid_reason)
        raise InvalidRecaptchaTokenError("The reCAPTCHA token is not valid.")

    # check if the expected action was executed
    if (recaptchaAction is not None):
        if (response.token_properties.action != recaptchaAction):
            raise InvalidRecaptchaActionError("The reCAPTCHA action is not valid.")

    # get the risk score and the reason(s)
    # For more information on interpreting the assessment,
    # see: https://cloud.google.com/recaptcha-enterprise/docs/interpret-assessment
    reasons = [reason for reason in response.risk_analysis.reasons]
    write_log_entry(
        logMessage={
            "reCAPTCHA information": {
                "token": recaptchaToken,
                "action": recaptchaAction,
                "score": response.risk_analysis.score,
                "reasons": json.dumps(reasons)
            }
        },
        severity="INFO"
    )
    return response

def score_within_acceptable_threshold(riskScore:int, threshold:float=0.5) -> bool:
    """
    Checks if the risk score is within the acceptable threshold.

    Args:
    - riskScore (int): The risk score of the reCAPTCHA token.
    - threshold (float): The acceptable threshold.
        - Range: 0.0 to 1.0
        - Defaults to 0.5
        - https://cloud.google.com/recaptcha-enterprise/docs/best-practices-oat

    Returns:
    - True if the risk score is within the acceptable threshold.
    - False if the risk score is not within the acceptable threshold.
    """
    return (threshold <= riskScore)

def write_log_entry(logName:str=CONSTANTS.LOGGING_NAME, logMessage:Union[str, dict]=None, severity:Optional[str]=None) -> None:
    """
    Writes an entry to the given log location.

    View logs here (Must be logged in):
    - _Default bucket
        - https://cloudlogging.app.goo.gl/Rr3GmcFNENq7nvBC6
    - coursefinity-web-app bucket
        - https://cloudlogging.app.goo.gl/G24TZQ7HqJF5dyk29

    Args:
    - logName (str): The location of the log to write to
        - Defaults to LOGGING_NAME defined in Constants.py
        - Will log to that location in the coursefinity-web-app bucket
            - I have already configured a sink to route logs with the name "coursefinity-web-app"
    - logMessage (str|dict): The message to write to the log
        - The message is written to the log with the given severity
        - More details on how to write the log messages:
            - https://cloud.google.com/logging/docs/samples/logging-write-log-entry
    - severity (str, optional): The severity of the log entry
        - If severity is defined in the dict type logMessage, you can leave the severity argument out
        - If the logMessage is a str, the severity argument is required
        - If severity is not defined, it will be set to "DEFAULT" severity
        - Available severity levels:
            - DEFAULT
            - DEBUG
            - INFO
            - NOTICE
            - WARNING
            - ERROR
            - CRITICAL
            - ALERT
            - EMERGENCY
        - More details on the severity type:
            - https://cloud.google.com/logging/docs/reference/v2/rest/v2/LogEntry#LogSeverity
    """
    if (logMessage is None):
        raise ValueError("logMessage must be defined!")

    if (severity is None):
        severity = "DEFAULT"
    elif (isinstance(severity, str) and severity.upper() in CONSTANTS.LOGGING_SEVERITY_TUPLE):
        severity = severity.upper()
    else:
        raise ValueError("severity must be a str or a valid severity!")

    app_root = Path(CONSTANTS.ROOT_FOLDER_PATH).parent
    stackLevel = 0
    stackTraceback = []

    try:
        while True:
            data = getframeinfo(stack()[stackLevel][0])
            if app_root not in Path(data.filename).parents: # Python packages expected to work
                break

            stackTraceback.append({
                "stackLevel": stackLevel,
                "filename": Path(data.filename).name,
                "lineNo": data.lineno,
                "function": f"{data.function}()" if data.function != "<module>" else data.function,
                "codeContext": [line.strip() for line in data.code_context],
                "index": data.index
            })
            stackLevel += 1
    except (IndexError):
        stackTraceback.append("No stack trace available!")

    logger = SECRET_CONSTANTS.LOGGING_CLIENT.logger(logName)
    if (isinstance(logMessage, dict)):
        if ("severity" not in logMessage):
            logMessage["severity"] = severity
        logMessage["stack_traceback"] = stackTraceback
        logger.log_struct(logMessage)
    elif (isinstance(logMessage, str)):
        logMessage = {"message": logMessage, "severity": severity, "stack_traceback": stackTraceback}
        logger.log_struct(logMessage)
    else:
        raise ValueError("logMessage must be a str or dict")

def generate_secure_random_bytes(nBytes:int=512, generateFromHSM:bool=False, returnHex:bool=False) -> Union[bytes, str]:
    """
    Generate a random byte/hex string of length nBytes that is cryptographicy secure.

    Args:
    - nBytes (int): The length of the byte string to generate.
        - Defaults to 512
    - generateFromHSM (bool): Whether to generate random bytes from
                              Google Cloud Platform KMS API's random number generated in the HSM.
        - Benefits for using Google Cloud Platform KMS API's random number generator:
            - The random number generator is generated in the HSM
            - Higher entropy than generating by your own
            - More details: https://cloud.google.com/kms/docs/generate-random
        - Defaults to False to use the secrets library to generate random bytes.
            - Recommended by OWASP to use secrets library to ensure higher entropy
            - More details: https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html#secure-random-number-generation
    - returnHex (bool): Whether to return the random bytes as a hex string.

    Returns:
    - A random byte string of length nBytes if returnHex is False.
    - A random hex string of length nBytes if returnHex is True.
    """
    if (nBytes < 1):
        raise ValueError("nBytes must be greater than 0!")

    # Since GCP KMS RNG Cloud HSM's minimum length is 8 bytes, 
    # fallback to secrets library if nBytes is less than 8
    if (not generateFromHSM or nBytes < 8):
        if (returnHex):
            return token_hex(nBytes)
        else:
            return token_bytes(nBytes)

    # Construct the location name
    locationName = SECRET_CONSTANTS.KMS_CLIENT.common_location_path(CONSTANTS.GOOGLE_PROJECT_ID, CONSTANTS.LOCATION_ID)

    # Check if the number of bytes exceeds GCP KMS RNG Cloud HSM limit
    if (nBytes > 1024):
        # if exceeded, make multiple API calls to generate the random bytes
        bytesArr = []
        maxBytes = 1024
        numOfMaxBytes = nBytes // maxBytes
        for _ in range(numOfMaxBytes):
            bytesArr.append(
                SECRET_CONSTANTS.KMS_CLIENT.generate_random_bytes(
                    request={
                        "location": locationName,
                        "length_bytes": maxBytes,
                        "protection_level": kms.ProtectionLevel.HSM
                    }
                )
            )

        remainder = nBytes % maxBytes
        if (remainder > 0):
            bytesArr.append(
                SECRET_CONSTANTS.KMS_CLIENT.generate_random_bytes(
                    request={
                        "location": locationName,
                        "length_bytes": remainder,
                        "protection_level": kms.ProtectionLevel.HSM
                    }
                )
            )
        randomBytes = b"".join(bytesArr)
    else:
        # Call the Google Cloud Platform API to generate a random byte string.
        randomBytesResponse = SECRET_CONSTANTS.KMS_CLIENT.generate_random_bytes(
            request={"location": locationName, "length_bytes": nBytes, "protection_level": kms.ProtectionLevel.HSM}
        )
        randomBytes = randomBytesResponse.data

    if (returnHex):
        return randomBytes.hex()
    else:
        return randomBytes

def get_key_info(keyRingID:str="", keyName:str="") -> resources.CryptoKey:
    """
    Get information about a key in Google Cloud KMS API.

    Args:
    - keyRingID (str): The ID of the key ring.
    - keyName (str): the name of the key to get information about

    Returns:
    - keyInfo (google.cloud.kms_v1.types.resources.CryptoKey): the key information
    """
    # Construct the key name
    keyName = SECRET_CONSTANTS.KMS_CLIENT.crypto_key_path(CONSTANTS.GOOGLE_PROJECT_ID, CONSTANTS.LOCATION_ID, keyRingID, keyName)

    # call Google Cloud KMS API to get the key's information
    response = SECRET_CONSTANTS.KMS_CLIENT.get_crypto_key(request={"name": keyName})
    return response

def crc32c(data:Union[bytes, str]) -> int:
    """
    Calculates the CRC32C checksum of the provided data

    Args:
    - data (str|bytes): the bytes of the data which the checksum should be calculated
        - If the data is in string format, it will be encoded to bytes

    Returns:
    - An int representing the CRC32C checksum of the provided bytes
    """
    return int(g_crc32c(initial_value=ensure_binary(data)).hexdigest(), 16)

def symmetric_encrypt(plaintext:Union[str, bytes]="", keyRingID:str=CONSTANTS.APP_KEY_RING_ID, keyID:str="") -> bytes:
    """
    Using Google Symmetric Encryption Algorithm, encrypt the provided plaintext.

    Args:
    - plaintext (str|bytes): the plaintext to encrypt
    - keyRingID (str): the key ring ID
        - Defaults to APP_KEY_RING_ID defined in Constants.py
    - keyID (str): the key ID/name of the key

    Returns:
    - ciphertext (bytes): the ciphertext
    """
    if (isinstance(plaintext, str)):
        plaintext = plaintext.encode("utf-8")

    # compute the plaintext's CRC32C checksum before sending it to Google Cloud KMS API
    plaintextCRC32C = crc32c(plaintext)

    # Construct the key version name
    keyVersionName = SECRET_CONSTANTS.KMS_CLIENT.crypto_key_path(
        CONSTANTS.GOOGLE_PROJECT_ID, CONSTANTS.LOCATION_ID, keyRingID, keyID
    )

    # construct and send the request to Google Cloud KMS API to encrypt the plaintext
    response = SECRET_CONSTANTS.KMS_CLIENT.encrypt(request={"name": keyVersionName, "plaintext": plaintext, "plaintext_crc32c": plaintextCRC32C})

    # Perform some integrity checks on the encrypted data that Google Cloud KMS API returned
    # details: https://cloud.google.com/kms/docs/data-integrity-guidelines
    if (not response.verified_plaintext_crc32c):
        # request sent to Google Cloud KMS API was corrupted in-transit
        raise CRC32ChecksumError("Plaintext CRC32C checksum does not match.")
    if (response.ciphertext_crc32c != crc32c(response.ciphertext)):
        # response received from Google Cloud KMS API was corrupted in-transit
        raise CRC32ChecksumError("Ciphertext CRC32C checksum does not match.")

    return response.ciphertext

def symmetric_decrypt(
    ciphertext:bytes=b"", 
    keyRingID:str=CONSTANTS.APP_KEY_RING_ID, 
    keyID:str="", 
    decode:Optional[bool]=True
) -> Union[str, bytes]:
    """
    Using Google Symmetric Encryption Algorithm, decrypt the provided ciphertext.

    Args:
    - ciphertext (bytes): the ciphertext to decrypt
    - keyRingID (str): the key ring ID
        - Defaults to APP_KEY_RING_ID defined in Constants.py
    - keyID (str): the key ID/name of the key
    - decode (bool): whether to decode the decrypted plaintext to string
        - Defaults to True

    Returns:
    - plaintext (str): the plaintext

    Raises:
    - CiphertextIsNotBytesError: If the ciphertext is not bytes
    - DecryptionError: If the decryption failed
    - CRC32ChecksumError: If the CRC32C checksum does not match
    """
    if (isinstance(ciphertext, bytearray)):
        ciphertext = bytes(ciphertext)

    if (not isinstance(ciphertext, bytes)):
        raise CiphertextIsNotBytesError(f"The ciphertext, {ciphertext} is in \"{type(ciphertext)}\" format. Please pass in a bytes type variable.")

    # Construct the key version name
    keyVersionName = SECRET_CONSTANTS.KMS_CLIENT.crypto_key_path(
        CONSTANTS.GOOGLE_PROJECT_ID, CONSTANTS.LOCATION_ID, keyRingID, keyID
    )

    # compute the ciphertext's CRC32C checksum before sending it to Google Cloud KMS API
    cipherTextCRC32C = crc32c(ciphertext)

    # construct and send the request to Google Cloud KMS API to decrypt the ciphertext
    try:
        response = SECRET_CONSTANTS.KMS_CLIENT.decrypt(request={"name": keyVersionName, "ciphertext": ciphertext, "ciphertext_crc32c": cipherTextCRC32C})
    except (GoogleErrors.InvalidArgument) as e:
        try:
            ciphertextToLog = urlsafe_b64encode(ciphertext).decode("utf-8")
        except:
            ciphertextToLog = "Could not url-safe base64 encode the ciphertext..."
        write_log_entry(
            logMessage={
                "Decryption Error": str(e),
                "URL-base64 Encoded Ciphertext": ciphertextToLog
            },
            severity="INFO"
        )
        raise DecryptionError("Symmetric Decryption failed.")

    # Perform a integrity check on the decrypted data that Google Cloud KMS API returned
    # details: https://cloud.google.com/kms/docs/data-integrity-guidelines
    if (response.plaintext_crc32c != crc32c(response.plaintext)):
        # response received from Google Cloud KMS API was corrupted in-transit
        raise CRC32ChecksumError("Plaintext CRC32C checksum does not match.")

    return response.plaintext.decode("utf-8") if (decode) else response.plaintext

class ExpiryProperties:
    """
    Class to format a timezone aware datetime object for expiry datetime used in tokens (NOT JWT).
    """
    def __init__(
        self,
        activeDuration:Optional[int]=0,
        strDate:Optional[str]=None,
        datetimeObj:Optional[datetime]=None
    ) -> None:
        """
        Initializes the ExpiryProperties object

        Args:
        - activeDuration (int, optional): the number of seconds the token is active.
        - strDate (str, optional): the date in the format of "YYYY-MM-DD HH:MM:SS".
        - datetimeObj (datetime, optional): the datetime object.
            - This datetime object must be timezone aware.
            - E.g. datetime.now().astimezone(tz=ZoneInfo("Asia/Singapore"))
        - Either one of the two parameters should be provided but NOT both.
        """
        if (strDate is None and activeDuration != 0 and datetimeObj is None):
            self.expiryDate = datetime.now().astimezone(tz=ZoneInfo("Asia/Singapore")) + timedelta(seconds=activeDuration)

        elif (strDate is not None and activeDuration == 0 and datetimeObj is None):
            self.expiryDate = datetime.strptime(strDate, CONSTANTS.DATE_FORMAT).astimezone(tz=ZoneInfo("Asia/Singapore"))

        elif (strDate is None and activeDuration == 0 and datetimeObj is not None):
            # check if datetimeObj is an instance of datetime class
            if (not isinstance(datetimeObj, datetime)):
                raise TypeError("datetimeObj must be an instance of datetime class")

            # check if datetimeObj is timezone aware
            if (datetimeObj.tzinfo is None):
                raise ValueError("datetimeObj must be timezone aware")

            # Once all the checks are done, set the expiryDate
            self.expiryDate = datetimeObj

        elif (strDate is not None and activeDuration != 0 and datetimeObj is not None):
            raise ValueError("Cannot specify both expirySeconds, strDate, and datetimeObj")

        else:
            raise ValueError("Either expirySeconds, strDate, or datetimeObj must be provided")

    def get_expiry_str_date(self) -> str:
        """
        Returns the expiry date in string type.

        E.g. "2022-06-26 17:21:20.123456 +0800"
        """
        return self.expiryDate.strftime(CONSTANTS.DATE_FORMAT)

    def is_expired(self) -> bool:
        """
        Returns True if the token has expired, False otherwise
        """
        return (datetime.now().astimezone(tz=ZoneInfo("Asia/Singapore")) > self.expiryDate)

    def __str__(self) -> str:
        return self.get_expiry_str_date()

    def __repr__(self) -> str:
        return self.get_expiry_str_date()

def compress_and_resize_image(
    imageData:IOBase=None, imagePath:pathlib.Path=None,
    dimensions:tuple=None, quality:int=100, optimise:bool=True,
    uploadToGoogleStorage:bool=True, bucketName:str=CONSTANTS.PUBLIC_BUCKET_NAME,
    folderPath:Optional[str]=None, cacheControl:Optional[str]=None
)-> str:
    """
    Resizes the image at the given path to the given dimensions and compresses it with the given quality.

    Converts the image to webp format as well for smaller image file size and saves the image to the given path.

    Args:
    - imageData (IOBase): The image data to compress and resize
    - imagePath (pathlib.Path): The path to the image to resize
    - dimensions (tuple): The dimensions to resize the image to
        - Must be a tuple of two integers, e.g. (500, 500)
    - quality (int): The quality of the image to resize to
        - Must be an integer between 1 and 100
        - Defaults to 100
    - optimise (bool): Whether to optimise the image or not
        - Defaults to True
    - uploadToGoogleStorage (bool): Whether to upload the image to Google Storage API or not
        - Defaults to True
    - bucketName (str): The name of the bucket to upload the image to on Google Storage API
        - Defaults to CONSTANTS.PUBLIC_BUCKET_NAME defined in Constants.py
    - folderPath (str, Optional): The path to the folder to save the image to on Google Storage API
        - E.g. "images" to save the image to "images/<imageName>"
        - If not provided, the image will be saved to the root folder of the bucket
    - cacheControl (str, Optional): The cache control header to set on the uploaded file.
        - E.g. "public, max-age=60" for a 1 minute cache
        - Default: None to use Google's default cache control of "public, max-age=3600"

    Returns:
    - The path to the compressed image (pathlib.Path)
    or the Google Storage public URL of the compressed image (str)

    Raises:
    - UnidentifiedImageError: If the image at the given path is not a valid image
    """
    try:
        # open image file
        if imageData is not None:
            imageData.seek(0) # reset the file pointer to the beginning of the file
            image = PillowImage.open(imageData).convert("RGB")
        else:
            image = PillowImage.open(imagePath).convert("RGB")
    except (PIL.UnidentifiedImageError) as e:
        print("Error in resizing and compressing image...")
        print("Error message caught:")
        print(e)
        raise InvalidProfilePictureError("The image is not a valid image file.")

    # resize image if dimensions are defined
    if (dimensions is not None):
        resizedImage = image.resize(dimensions)
    else:
        resizedImage = image

    # changes the extension to .webp
    imagePath = imagePath.with_suffix(".webp")

    if (not uploadToGoogleStorage):
        # remove the image file if user has already uploaded one before
        imagePath.unlink(missing_ok=True)

        # save the new and compressed image as webp
        resizedImage.save(imagePath, format="webp", optimize=optimise, quality=quality)

        # Return the pathlib.Path object of the new and compressed image
        return imagePath

    # Save the new and compressed image as webp to the stream buffer
    fileObj = BytesIO()
    resizedImage.save(fileObj, format="webp", optimize=optimise, quality=quality)
    fileObj.seek(0) # reset the file pointer to the beginning of the file

    # upload the new and compressed image to Google Storage
    # and return the public url of the uploaded image
    destinationPath = "/".join([folderPath, imagePath.name]) if (folderPath is not None) else imagePath.name
    return upload_from_stream(
        bucketName=bucketName, fileObj=fileObj, uploadDestination=destinationPath, cacheControl=cacheControl
    )

def upload_new_secret_version(secretID:Union[str, bytes]=None, secret:str=None, destroyPastVer:bool=False, destroyOptimise:bool=False) -> None:
    """
    Uploads the new secret to Google Cloud Platform's Secret Manager API.

    Args:
    - secretID (str): The ID of the secret to upload
    - secret (str|bytes): The secret to upload
    - destroyPastVer (bool): Whether to destroy the past version of the secret or not
    - destroyOptimise (bool): Whether to optimise the process of destroying the past version of the secret
        - Note: This should be True if the past versions have been consistently destroyed
            - Example 1: destoryOptimise should be False to ensure all versions have been destroyed
                - version 1: destroyed
                - version 2: active
                - version 3: destroyed
                - new version: active
            - Example 2: destroyOptimise should be True as there will be only 2 iterations
                      of the loop when destorying the past version instead of 3
                - version 1: destroyed
                - version 2: destroyed
                - version 3: active
                - new version: active
    """
    # construct the secret path to the secret key ID
    secretPath = SECRET_CONSTANTS.SM_CLIENT.secret_path(CONSTANTS.GOOGLE_PROJECT_ID, secretID)

    # encode the secret to bytes if secret is in string format
    if (isinstance(secret, str)):
        secret = secret.encode()

    # calculate the payload crc32c checksum
    crc32cChecksum = crc32c(secret)

    # Add the secret version and send to Google Secret Management API
    response = SECRET_CONSTANTS.SM_CLIENT.add_secret_version(parent=secretPath, payload={"data": secret, "data_crc32c": crc32cChecksum})

    # get the latest secret version
    latestVer = int(response.name.split("/")[-1])
    write_log_entry(
        logMessage={
            "message": f"Secret {secretID} (version {latestVer}) created successfully!",
            "details": response
        },
        severity="INFO"
    )

    # disable all past versions if destroyPastVer is True
    if (destroyPastVer):
        for version in range(latestVer - 1, 0, -1):
            secretVersionPath = SECRET_CONSTANTS.SM_CLIENT.secret_version_path(CONSTANTS.GOOGLE_PROJECT_ID, secretID, version)
            try:
                SECRET_CONSTANTS.SM_CLIENT.destroy_secret_version(request={"name": secretVersionPath})
            except (GoogleErrors.FailedPrecondition):
                # key is already destroyed
                if (destroyOptimise):
                    break
        write_log_entry(
            logMessage=f"Successfully destroyed all past versions of the secret {secretID}",
            severity="INFO"
        )

def create_message(
    sender:str="coursefinity123@gmail.com", to:str="", subject:str="", message:str="", name:Optional[str]=None
) -> dict:
    """
    Create a message for an email.

    Args:
    - sender (str): Email address of the sender.
    - to (str): Email address of the receiver.
    - subject (str): The subject of the email message.
    - message (str): The text of the email message. (Can be HTML)
    - name (str, Optional): The name of the recipient.

    Returns:
    A dictionary containing a base64url encoded email object.
    """
    htmlMessage = MIMEMultipart(_subtype="related")
    mainBody = f"""<p>Hello{f' {name}' if (name is not None) else ''},</p>

{message}

<p>
    Sincerely,<br>
    <strong>CourseFinity Support Team</strong>
</p>
<img src="https://storage.googleapis.com/coursefinity/web-assets/common/filled_logo.png" alt="CourseFinity Logo" style="border-radius: 5px; width: min(250px, 40%);">
"""
    htmlMessage.attach(MIMEText(mainBody, _subtype="html"))

    htmlMessage["To"] = to
    htmlMessage["From"] = sender
    htmlMessage["Subject"] = " ".join(["[CourseFinity]", subject])
    return {"raw": urlsafe_b64encode(htmlMessage.as_string().encode()).decode()}

def send_email(to:str="", subject:str="", body:str="", name:Optional[str]=None) -> Union[dict, None]:
    """
    Create and send an email message.

    Args:
    - to (str): Email address of the receiver.
    - subject (str): The subject of the email message.
    - body (str): The text of the email message. (Can be HTML)
    - name (str, Optional): The name of the recipient.

    Returns:
    Message object, including message id or None if there was an error.
    """
    sentMessage = None
    try:
        # creates a message object and sets the sender, recipient, and subject.
        message = create_message(to=to, subject=subject, message=body, name=name)

        # Get the Google Gmail API authorised instance.
        GMAIL_CLIENT = get_gmail_client()

        # send the message
        sentMessage = (GMAIL_CLIENT.users().messages().send(userId="me", body=message).execute())
        print(f"Email sent!")
    except HttpError as e:
        print("Failed to send email...")
        write_log_entry(
            logMessage=f"Email titled {subject} cannot be sent: {e}",
            severity="ERROR"
        )

    return sentMessage

def get_gmail_client() -> Resource:
    """
    Initialise Google API by trying to authenticate with token.json
    On success, will not ask for credentials again.
    Otherwise, will ask to authenticate with Google.

    Returns:
    - Google API resource object
    """
    # If modifying these scopes, delete the file token.json.
    # Scopes details: https://developers.google.com/gmail/api/auth/scopes
    SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

    # get the token.json file from Google Cloud Secret Manager API
    GOOGLE_TOKEN = json.loads(SECRET_CONSTANTS.get_secret_payload(secretID=CONSTANTS.GOOGLE_TOKEN_NAME))
    write_log_entry(
        logMessage=f"Deserialisation : Get Gmail Client Token",
        severity="NOTICE"
    )
    creds = Credentials.from_authorized_user_info(GOOGLE_TOKEN, SCOPES)

    # Build the Gmail service from the credentials and return it
    return build("gmail", "v1", credentials=creds)

def pwd_is_strong(password:str, strict:bool=False) -> bool:
    """
    Checks if the password is strong against the password regex.

    Args:
    - password (str): The password to check.
    - strict (bool): Whether to match all minimum requirements.
        - Used when haveibeenpwned's API is unavailable.

    Returns:
    - True if the password is strong, False otherwise.

    Password complexity minimum requirements (must match at least 3):
    - At least 10 characters long
    - At least one lowercase letter
    - At least one uppercase letter
    - At least one digit
    - At least one special character
    - Not more than two identical characters in a row

    Resources:
    - https://owasp.org/www-community/password-special-characters
    - https://owasp.deteact.com/cheat/cheatsheets/Authentication_Cheat_Sheet.html#password-complexity
    """
    if (strict):
        return (re.fullmatch(CONSTANTS.STRICT_PASSWORD_REGEX, password) is not None)

    strength = 0
    if (re.fullmatch(CONSTANTS.LENGTH_REGEX, password)):
        strength += 1

    if (re.match(CONSTANTS.LOWERCASE_REGEX, password)):
        strength += 1

    if (re.match(CONSTANTS.UPPERCASE_REGEX, password)):
        strength += 1

    if (re.match(CONSTANTS.DIGIT_REGEX, password)):
        strength += 1

    if (re.match(CONSTANTS.SPECIAL_CHAR_REGEX, password)):
        strength += 1

    if (re.fullmatch(CONSTANTS.TWO_REPEAT_CHAR_REGEX, password)):
        strength += 1

    if (re.fullmatch(CONSTANTS.ALLOWED_CHAR_REGEX, password) is None):
        return False # return false if the password contains any characters that are not allowed

    return (strength >= 3)

def pwd_has_been_pwned(password:str) -> Union[bool, tuple]:
    """
    Checks if the password is in the haveibeenpwned database.
    If it is found, it means that the password is weak and has been
    leaked in the dark web through breaches from other services/websites.

    Args:
    - password (str): The password to check

    Returns:
    - True if the password is in the database, False otherwise.
    - In the event that the API is down, it will return a tuple.
    """
    # hash the password (plaintext) using sha1 to check
    # against haveibeenpwned's database
    # but will not be stored in the MySQL database
    passwordHash = sha1(password.encode("utf-8")).hexdigest().upper()
    hashPrefix = passwordHash[:5]
    hashSuffix = passwordHash[5:]
    del passwordHash

    # retrieve the list of possible range from the api database
    # using the first five characters (to get the hash prefix) of the sha1 hash.
    results = []
    while (1):
        response = req.get(f"https://api.pwnedpasswords.com/range/{hashPrefix}")
        if (response.status_code == 200):
            results = response.text.splitlines()
            break
        elif (response.status_code == 429):
            # haveibeenpwned API is rate limited, so wait for a while and try again
            print(f"Failed to retrieve data from api.pwnedpasswords.com. Retrying in 1 seconds...")
            sleep(0.5)
        else:
            write_log_entry(
                logMessage=f"Failed to retrieve data from api.pwnedpasswords.com. Error code: {response.status_code}",
                severity="NOTICE"
            )
            # if the api is unavailable, will rely on the
            # checking of the password strength very strictly
            # i.e. must meet all the minimum requirements
            # if user is signing up or changing password
            return (pwd_is_strong(password, strict=True), "strict")

    # compare the possible ranges with the hash suffix (after the first five characters) of the sha1 hash
    for result in results:
        if (result.split(":")[0] == hashSuffix):
            # if the password has been found, return True
            return True
    return False

def generate_id(sixteenBytesTimes:Optional[int]=1) -> str:
    """
    Generates a unique ID (16 bytes)

    Args:
    - sixteenBytesTimes (int, Optional): The number of times to generate a 16 byte ID and combines them,
        - Defaults to 1
        - E.g. sixteenBytesTimes=2 will generate a uuid4 hex string of 16 bytes twice and combine them
    """
    if (sixteenBytesTimes == 1):
        return uuid.uuid4().hex
    elif (sixteenBytesTimes > 1):
        return "".join([uuid.uuid4().hex for _ in range(sixteenBytesTimes)])
    else:
        # less than 1
        raise ValueError("The number of times to generate a 16 byte ID must be greater than 0.")