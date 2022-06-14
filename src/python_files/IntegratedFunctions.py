# import python standard libraries
import uuid, sqlite3, json
from datetime import datetime
from typing import Union
from base64 import urlsafe_b64encode

# import third party libraries
from dicebear import DAvatar, DStyle

# import local python files
from .Course import Course
from .Google import google_init, SCOPES, TOKEN_PATH

# For Gmail API (Third-party libraries)
from email.mime.text import MIMEText
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials

# import Flask web application configs
from __init__ import app

google_init() # ensure that there is token.json for gmail API

def create_message(sender:str="coursefinity123@gmail.com", to:str="", subject:str="", messageText:str="") -> dict:
    """
    Create a message for an email.
    
    Args:
    - sender: Email address of the sender.
    - to: Email address of the receiver.
    - subject: The subject of the email message.
    - messageText: The text of the email message. (Can be HTML)

    Returns:
    A dictionary containing a base64url encoded email object.
    """
    message = MIMEText(messageText, "html")
    message["To"] = to
    message["From"] = sender
    message["Subject"] = subject
    return {"raw": urlsafe_b64encode(message.as_string().encode()).decode()}

def send_email(to:str="", subject:str="", messageText:str="") -> Union[dict, None]:
    """
    Create and send an email message.
    
    Args:
    - to: Email address of the receiver.
    - subject: The subject of the email message.
    - messageText: The text of the email message. (Can be HTML)
    
    Returns: 
    Message object, including message id or None if there was an error.
    """
    creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    sentMessage = None
    try:
        # Create an authorized Gmail API service instance.
        service = build("gmail", "v1", credentials=creds)

        # creates a message object and sets the sender, recipient, and subject.
        message = create_message(to=to, subject=subject, messageText=messageText)

        # send the message
        sentMessage = (service.users().messages().send(userId="me", body=message).execute())
        print(f"Email sent!")
    except HttpError as e:
        print("Failed to send email...")
        print(f"Error:\n{e}\n")

    return sentMessage

def generate_id() -> str:
    """
    Generates a unique ID
    """
    return uuid.uuid4().hex

def get_image_path(userID:str, returnUserInfo:bool=False) -> Union[str, tuple]:
    """
    Returns the image path for the user.
    
    If the user does not have a profile image uploaded, it will return a dicebear url.
    Else, it will return the relative path of the user's profile image.
    
    If returnUserInfo is True, it will return a tuple of the user's record.
    
    Args:
        - userID: The user's ID
        - returnUserInfo: If True, it will return a tuple of the user's record.
    """
    userInfo = sql_operation(table="user", mode="get_user_data", userID=userID)
    imageSrcPath = userInfo[5]
    if (not imageSrcPath):
        imageSrcPath = get_dicebear_image(userInfo[2])
    return imageSrcPath if (not returnUserInfo) else (imageSrcPath, userInfo)

def get_dicebear_image(username:str) -> str:
    """
    Returns a random dicebear image from the database
    
    Args:
        - username: The username of the user
    """
    av = DAvatar(
        style=DStyle.initials,
        seed=username,
        options=app.config["DICEBEAR_OPTIONS"]
    )
    return av.url_svg

def sql_operation(table:str=None, mode:str=None, **kwargs) -> Union[str, list, tuple, bool, dict, None]:
    """
    Connects to the database and returns the connection object
    
    Args:
        - table: The table to connect to ("course", "user")
        - mode: The mode to use ("insert", "edit", "login", etc.)
        - kwargs: The keywords to pass into the respective sql operation functions
    
    Returns the returned value from the SQL operation.
    """
    returnValue = None
    # timeout is in seconds to give time to other threads that is connected to the SQL database.
    # After the timeout, an OperationalError will be raised, stating "database is locked".
    con = sqlite3.connect(app.config["SQL_DATABASE"], timeout=10)
    if (table == "user"):
        returnValue = user_sql_operation(connection=con, mode=mode, **kwargs)
    elif (table == "course"):
        returnValue = course_sql_operation(connection=con, mode=mode, **kwargs)
    # elif table == "cart":
    #     returnValue = cart_sql_operation(connection=con, mode=mode, **kwargs)
    # elif table == "purchased":
    #     returnValue = purchased_sql_operation(connection=con, mode=mode, **kwargs)

    con.close()
    return returnValue

def user_sql_operation(connection:sqlite3.Connection, mode:str=None, **kwargs) -> Union[str, tuple, bool, dict, None]:
    """
    Do CRUD operations on the user table
    
    insert keywords: email, username, password
    login keywords: email, password
    get_user_data keywords: userID
    edit keywords: userID, username, password, email, profileImagePath
    add_to_cart keywords: userID, courseID
    remove_from_cart keywords: userID, courseID
    purchase_courses keywords: userID
    delete keywords: userID
    """
    if (not mode):
        raise ValueError("You must specify a mode in the user_sql_operation function!")

    cur = connection.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS user (
        id PRIMARY KEY, 
        role TEXT NOT NULL,
        username TEXT NOT NULL UNIQUE, 
        email TEXT NOT NULL UNIQUE, 
        password TEXT NOT NULL, 
        profile_image TEXT, 
        date_joined DATE NOT NULL,
        card_name TEXT,
        card_no INTEGER, -- May not be unique since one might have alt accounts.
        card_exp TEXT,
        card_cvv INTEGER,
        cart_courses TEXT NOT NULL,
        purchased_courses TEXT NOT NULL
    )""")
    if (mode == "verify_userID_existence"):
        userID = kwargs.get("userID")
        if (not userID):
            raise ValueError("You must specify a userID in the user_sql_operation function when verifying userID!")
        cur.execute("SELECT * FROM user WHERE id=?", (userID,))
        return bool(cur.fetchone())

    elif (mode == "insert"):
        emailInput = kwargs.get("email")
        usernameInput = kwargs.get("username")

        emailDupe = bool(cur.execute(f"SELECT * FROM user WHERE email='{emailInput}'").fetchall())

        usernameDupes = bool(cur.execute(f"SELECT * FROM user WHERE username='{usernameInput}'").fetchall())

        if (emailDupe or usernameDupes):
            return (emailDupe, usernameDupes)

        # add to the sqlite3 database
        userID = generate_id()
        passwordInput = kwargs.get("password")
        data = (userID, "Student", usernameInput, emailInput, passwordInput, None, datetime.now().strftime("%Y-%m-%d"), None, None, None, None, "[]", "[]")
        cur.execute("INSERT INTO user VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", data)
        connection.commit()
        return userID

    elif (mode == "login"):
        emailInput = kwargs.get("email")
        passwordInput = kwargs.get("password")
        cur.execute(f"SELECT id, role FROM user WHERE email='{emailInput}' AND password='{passwordInput}'")
        matched = cur.fetchone()
        if (not matched):
            return False
        return matched

    elif (mode == "get_user_data"):
        userID = kwargs.get("userID")
        cur.execute(f"SELECT * FROM user WHERE id='{userID}'")
        matched = cur.fetchone()
        if (not matched):
            return False
        return matched

    elif (mode == "edit"):
        userID = kwargs.get("userID")
        usernameInput = kwargs.get("username")
        emailInput = kwargs.get("email")
        oldPasswordInput = kwargs.get("oldPassword")
        passwordInput = kwargs.get("password")
        profileImagePath = kwargs.get("profileImagePath")
        newAccType = kwargs.get("newAccType") # pass in a boolean to indicate whether to update to Teacher

        cardName = kwargs.get("cardName")
        cardNo = kwargs.get("cardNo")
        cardExp = kwargs.get("cardExpiry")
        cardCvv = kwargs.get("cardCVV")

        statement = "UPDATE user SET "
        if (usernameInput is not None):
            duplicates = (f"SELECT * FROM user WHERE username='{usernameInput}'")
            cur.execute(duplicates)
            matched = cur.fetchone()
            if (not matched):
                statement += f"username='{usernameInput}' "
            else:
                return False

        if (emailInput is not None):
            duplicates = (f"SELECT * FROM user WHERE email='{emailInput}'")
            cur.execute(duplicates)
            matched = cur.fetchone()
            if (not matched):
                statement += f"email='{emailInput}' "
            else:
                return False

        if (passwordInput is not None):
            duplicates = (f"SELECT password FROM user WHERE id='{userID}'")
            cur.execute(duplicates)
            userPassword = cur.fetchone()[0]
            if (userPassword == oldPasswordInput):
                if (userPassword != passwordInput):
                    statement += f"password='{passwordInput}' "
                else:
                    return "Cannot Reuse previous password!"
            else:
                return "Password does not match previous password!"

        if (profileImagePath is not None):
            statement += f"profile_image='{profileImagePath}' "

        if (newAccType is not None):
            statement += "role='Teacher' "

        if (cardName is not None):
            statement += f"card_name='{cardName}', card_no='{cardNo}', card_exp='{cardExp}', card_cvv='{cardCvv}' "

        statement += f"WHERE id='{userID}'"
        print(statement)
        cur.execute(statement)
        connection.commit()

    elif (mode == "delete"):
        userID = kwargs.get("userID")
        cur.execute(f"DELETE FROM user WHERE id='{userID}'")
        connection.commit()

    elif (mode == "get_user_purchases"):
        userID = kwargs.get("userID")
        cur.execute(f"SELECT purchased_courses FROM user WHERE id='{userID}'")
        return json.loads(cur.fetchone()[0])

    elif mode == "get_user_cart":
        userID = kwargs.get("userID")
        cur.execute(f"SELECT cart_courses FROM user WHERE id='{userID}'")
        return json.loads(cur.fetchone()[0])

    elif mode == "add_to_cart":
        
        userID = kwargs.get("userID")
        courseID = kwargs.get("courseID")

        cur.execute(f"SELECT cart_courses FROM user WHERE id='{userID}'")
        cartCourseIDs = json.loads(cur.fetchone()[0])

        cur.execute(f"SELECT purchased_courses FROM user WHERE id='{userID}'")
        purchasedCourseIDs = json.loads(cur.fetchone()[0])
        
        if courseID not in cartCourseIDs and courseID not in purchasedCourseIDs:
            cartCourseIDs.append(courseID)
            cur.execute(f"UPDATE user SET cart_courses='{json.dumps(cartCourseIDs)}' WHERE id='{userID}'")
            connection.commit()

    elif mode == "remove_from_cart":
        userID = kwargs.get("userID")
        courseID = kwargs.get("courseID")

        cur.execute(f"SELECT cart_courses FROM user WHERE id='{userID}'")
        cartCourseIDs = json.loads(cur.fetchone()[0])

        if courseID in cartCourseIDs:
            cartCourseIDs.remove(courseID)
            cur.execute(f"UPDATE user SET cart_courses='{json.dumps(cartCourseIDs)}' WHERE id='{userID}'")
            connection.commit()

    elif mode == "purchase_courses":

        userID = kwargs.get("userID")

        cur.execute(f"SELECT cart_courses FROM user WHERE id='{userID}'")
        cartCourseIDs = json.loads(cur.fetchone()[0])

        cur.execute(f"SELECT purchased_courses FROM user WHERE id='{userID}'")
        purchasedCourseIDs = json.loads(cur.fetchone()[0])

        for courseID in cartCourseIDs:
        
            if courseID not in purchasedCourseIDs:
                purchasedCourseIDs.append(courseID)
        
        # Add to purchases
        cur.execute(f"UPDATE user SET purchased_courses='{json.dumps(purchasedCourseIDs)}' WHERE id='{userID}'")        
        
        # Empty cart
        cur.execute(f"UPDATE user SET cart_courses='[]' WHERE id='{userID}'")

        connection.commit()

    elif (mode == "check_card_if_exist"):
        userID = kwargs.get("userID")
        getCardInfo = kwargs.get("getCardInfo")

        cur.execute(f"SELECT card_name, card_no, card_exp, card_cvv FROM user WHERE id='{userID}'")
        cardInfo = cur.fetchone()
        if (cardInfo is None):
            return False

        if (cardInfo[0] is None or cardInfo[1] is None or cardInfo[2] is None or cardInfo[3] is None):
            return False

        if (not getCardInfo):
            return True
        return (cardInfo, True)

    elif (mode == "delete_card"):
        userID = kwargs.get("userID")
        cur.execute(f"UPDATE user SET card_name=NULL, card_no=NULL, card_exp=NULL, card_cvv=NULL WHERE id='{userID}'")
        connection.commit()
    elif (mode == "update_card"):
        userID = kwargs.get("userID")
        cardExp = kwargs.get("cardExpiry")
        cardCvv = kwargs.get("cardCVV")
        cur.execute(f"UPDATE user SET card_exp='{cardExp}', card_cvv='{cardCvv}' WHERE id='{userID}'")
        connection.commit()

# May not be used
def course_sql_operation(connection:sqlite3.Connection=None, mode:str=None, **kwargs)  -> Union[list, tuple, bool, None]:
    """
    Do CRUD operations on the course table
    
    insert keywords: teacherID
    
    get_course_data keywords: courseID

    edit keywords: 
    """
    if (not mode):
        raise ValueError("You must specify a mode in the course_sql_operation function!")

    cur = connection.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS course (
        course_id PRIMARY KEY, 
        teacher_id TEXT NOT NULL,
        course_name TEXT NOT NULL,
        course_description TEXT,
        course_image_path TEXT,
        course_price FLOAT NOT NULL,
        course_category TEXT NOT NULL,
        course_total_rating INT NOT NULL,
        course_rating_count INT NOT NULL,
        date_created DATE NOT NULL,
        video_path TEXT NOT NULL,
        FOREIGN KEY (teacher_id) REFERENCES user(id)
    )""")
    if (mode == "insert"):
        course_id = generate_id()
        teacher_id = kwargs.get("teacherId")
        course_name = kwargs.get("courseName")
        course_description = kwargs.get("courseDescription")
        course_image_path = kwargs.get("courseImagePath")
        course_price = kwargs.get("coursePrice")
        course_category = kwargs.get("courseCategory")
        video_path = kwargs.get("videoPath")
        course_total_rating = 0
        course_rating_count = 0
        date_created = datetime.now().strftime("%Y-%m-%d")
        
        data = (course_id, teacher_id, course_name, course_description, course_image_path, course_price, course_category, course_total_rating, course_rating_count, date_created, video_path)
        cur.execute("INSERT INTO course VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", data)
        connection.commit()

    elif (mode == "get_course_data"):
        course_id = kwargs.get("courseID")
        print(course_id)
        cur.execute(f"SELECT * FROM course WHERE course_id='{course_id}'")
        matched = cur.fetchone()
        print(matched)
        if (not matched):
            return False
        return matched

    elif (mode == "edit"):
        course_id = kwargs.get("courseID")
        course_name = kwargs.get("courseName")
        course_description = kwargs.get("courseDescription")
        course_image_path = kwargs.get("courseImagePath")
        course_price = kwargs.get("coursePrice")
        course_category = kwargs.get("courseCategory")
        course_total_rating = kwargs.get("courseTotalRating")
        course_rating_count = kwargs.get("courseRatingCount")

    elif (mode == "delete"):
        course_id = kwargs.get("courseID")
        cur.execute(f"DELETE FROM course WHERE course_id='{course_id}'")
        connection.commit()

    elif (mode == "get_3_latest_courses" or mode == "get_3_highly_rated_courses"):
        teacherID = kwargs.get("teacherID")
        statement = "SELECT course_id, teacher_id, course_name, course_description, course_image_path, course_price, course_category, date_created, course_total_rating, course_rating_count FROM course "

        if (mode == "get_3_latest_courses"):
            # get the latest 3 courses
            if (not teacherID):
                cur.execute(f"{statement} ORDER BY ROWID DESC LIMIT 3")
            else:
                cur.execute(f"{statement} WHERE teacher_id='{teacherID}' ORDER BY ROWID DESC LIMIT 3")
        else:
            # get top 3 highly rated courses
            if (not teacherID):
                cur.execute(f"{statement} ORDER BY (course_total_rating/course_rating_count) DESC LIMIT 3")
            else:
                cur.execute(f"{statement} WHERE teacher_id='{teacherID}' ORDER BY (course_total_rating/course_rating_count) DESC LIMIT 3")

        matchedList = cur.fetchall()
        if (not matchedList):
            return []
        else:
            # e.g. [(("Daniel", "daniel_profile_image"), (course_id, teacher_name, course_name,...))]
            courseInfoList = []
            # get the teacher name for each course
            if (not teacherID):
                teacherIDList = [teacherID[1] for teacherID in matchedList]
                for i, teacherID in enumerate(teacherIDList):
                    res = cur.execute(f"SELECT username, profile_image FROM user WHERE id='{teacherID}'").fetchone()
                    teacherUsername = res[0]
                    teacherProfile = res[1]
                    teacherProfile = (get_dicebear_image(teacherUsername), True) if (not teacherProfile) \
                                                                                else (teacherProfile, False)
                    courseInfoList.append(Course(((teacherUsername, teacherProfile), matchedList[i])))
                return courseInfoList
            else:
                res = cur.execute(f"SELECT username, profile_image FROM user WHERE id='{teacherID}'").fetchone()
                teacherUsername = res[0]
                teacherProfile = res[1]
                teacherProfile = (get_dicebear_image(teacherUsername), True) if (not teacherProfile) \
                                                                            else (teacherProfile, False)
                for tupleInfo in matchedList:
                    courseInfoList.append(Course(((teacherUsername, teacherProfile), tupleInfo)))
                
                if (kwargs.get("getTeacherUsername")):
                    return (courseInfoList, res[0])

                return courseInfoList

    elif (mode == "search"):
        searchInput = kwargs.get("searchInput")
        resultsList = []

        foundResults = cur.execute(f"SELECT course_id, teacher_id, course_name, course_description, course_image_path, course_price, course_category, date_created, course_total_rating, course_rating_count FROM course WHERE course_name LIKE '%{searchInput}%'").fetchall()
        teacherIDList = [teacherID[1] for teacherID in foundResults]
        for i, teacherID in enumerate(teacherIDList):
            res = cur.execute(f"SELECT username, profile_image FROM user WHERE id='{teacherID}'").fetchone()
            teacherUsername = res[0]
            teacherProfile = res[1]
            teacherProfile = (get_dicebear_image(teacherUsername), True) if (not teacherProfile) \
                                                                         else (teacherProfile, False)
            resultsList.append(Course(((teacherUsername, teacherProfile), foundResults[i])))

        return resultsList

# May not be used
def cart_sql_operation(connection:sqlite3.Connection=None, mode:str=None, **kwargs) -> Union[list, None]:
    """
    Do CRUD operations on the cart table
    
    insert keywords: userID, courseID
    get_cart_data keywords: userID
    remove keywords: userID, courseID
    empty keywords: userID
    """

    if mode == None:
        raise ValueError("You must specify a mode in the cart_sql_operation function!")

    cur = connection.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS cart (
        user_id TEXT,
        course_id TEXT,
        PRIMARY KEY (user_id, course_id)
    )""")

    userID = kwargs.get("userID")

    if mode == "insert":
        courseID = kwargs.get("courseID")
        cur.execute("INSERT INTO cart VALUES (?, ?)", (userID, courseID))
        connection.commit()

    elif mode == "get_cart_courses":
        # List of course IDs in cart
        courseID_list = cur.execute(f"SELECT course_id FROM cart WHERE user_id = '{userID}'").fetchall()
        return courseID_list

    elif mode == "remove":
        courseID = kwargs.get("courseID")
        cur.execute("DELETE FROM cart WHERE user_id = '{userID}' AND course_id = '{courseID}'")
        connection.commit()

    elif mode == "empty":
        cur.execute("DELETE FROM cart WHERE user_id = '{userID}'")
        connection.commit()
    
# May not be used
def purchased_sql_operation(connection:sqlite3.Connection=None, mode:str=None, **kwargs) -> Union[list, None]:
    """
    Do CRUD operations on the purchased table
    
    insert keywords: userID, courseID
    get_purchased_data keywords: userID
    delete keywords: userID, courseID
    """

    if mode == None:
        raise ValueError("You must specify a mode in the purchased_sql_operation function!")

    cur = connection.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS purchased (
        user_id TEXT,
        course_id TEXT,
        PRIMARY KEY (user_id, course_id)
    )""")

    userID = kwargs.get("userID")

    if mode == "insert":
        courseID = kwargs.get("courseID")
        cur.execute("INSERT INTO purchased VALUES (?, ?)", (userID, courseID))
        connection.commit()

    elif mode == "get_purchased_courses":
        # List of course IDs in purchased
        courseID_list = cur.execute(f"SELECT course_id FROM purchased WHERE user_id = '{userID}'").fetchall()
        return courseID_list

    elif mode == "delete":
        courseID = kwargs.get("courseID")
        cur.execute("DELETE FROM purchased WHERE user_id = '{userID}' AND course_id = '{courseID}'")
        connection.commit()

def review_sql_operation(connection:sqlite3.Connection=None, mode: str=None, **kwargs) -> Union[list, None]:
    """
    Do CRUD operations on the purchased table

    revieve keywords: userID, courseID, 
    insert keywords: userID, courseID, courseRating, CourseReview
    
    """
    if mode == None:
        raise ValueError("You must specify a mode in the review_sql_operation function!")
    
    cur = connection.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS review (
        user_id TEXT,
        course_id TEXT,
        course_rating INTEGER,
        course_review TEXT,
        
        PRIMARY KEY (user_id, course_id)
    )""")

    userID = kwargs.get("userID")
    courseID = kwargs.get("courseID")

    if mode == "retrieve":
        review_list = cur.execute(f"SELECT course_rating, course_review FROM review WHERE user_id = '{userID}' AND course_id = '{courseID}'").fetchall()
        return review_list
    
    if mode == "insert":
        courseRating = kwargs.get("courseRating")
        courseReview = kwargs.get("courseReview")
        cur.execute("INSERT INTO review VALUES (?, ?, ?, ?)", (userID, courseID, courseRating, courseReview))
        connection.commit()