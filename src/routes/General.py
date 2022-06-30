"""
Routes for the general public and CourseFinity users (Guests, Students, Teachers, and Admins)
"""
# import third party libraries
import markdown

# import flask libraries (Third-party libraries)
from flask import render_template, request, session, abort, Blueprint

# import local python libraries
from python_files.SQLFunctions import *
from python_files.Reviews import Reviews

generalBP = Blueprint("generalBP", __name__, static_folder="static", template_folder="template")

@generalBP.route("/")
def home():
    latestThreeCourses = sql_operation(table="course", mode="get_3_latest_courses")
    threeHighlyRatedCourses = sql_operation(table="course", mode="get_3_highly_rated_courses")

    userPurchasedCourses = []
    accType = imageSrcPath = None
    if ("user" in session):
        imageSrcPath, userInfo = get_image_path(session["user"], returnUserInfo=True)
        userPurchasedCourses = userInfo[-1]
        accType = userInfo[1]
    elif ("admin" in session):
        accType = "Admin"

    return render_template("users/general/home.html", imageSrcPath=imageSrcPath,
        userPurchasedCourses=userPurchasedCourses,
        threeHighlyRatedCourses=threeHighlyRatedCourses, threeHighlyRatedCoursesLen=len(threeHighlyRatedCourses),
        latestThreeCourses=latestThreeCourses, latestThreeCoursesLen=len(latestThreeCourses), accType=accType)

@generalBP.route("/teacher/<string:teacherID>")
def teacherPage(teacherID:str):
    latestThreeCourses = sql_operation(table="course", mode="get_3_latest_courses", teacherID=teacherID, getTeacherUsername=False)
    threeHighlyRatedCourses, teacherUsername = sql_operation(table="course", mode="get_3_highly_rated_courses", teacherID=teacherID, getTeacherUsername=True)

    teacherProfilePath = get_image_path(teacherID)

    accType = imageSrcPath = None
    userPurchasedCourses = {}
    if ("user" in session):
        imageSrcPath, userInfo = get_image_path(session["user"], returnUserInfo=True)
        userPurchasedCourses = userInfo[-1]
        accType = userInfo[1]

    return render_template("users/general/teacher_page.html",
        imageSrcPath=imageSrcPath, userPurchasedCourses=userPurchasedCourses, teacherUsername=teacherUsername,
        teacherProfilePath=teacherProfilePath,
        threeHighlyRatedCourses=threeHighlyRatedCourses, threeHighlyRatedCoursesLen=len(threeHighlyRatedCourses),
        latestThreeCourses=latestThreeCourses, latestThreeCoursesLen=len(latestThreeCourses), accType=accType)

@generalBP.route("/course/<string:courseID>")
def coursePage(courseID:str):
    print(courseID)
    #courseID = "a78da127690d40d4bebaf5d9c45a09a8"
    # the course id is
    #   a78da127690d40d4bebaf5d9c45a09a8
    courses = sql_operation(table="course", mode="get_course_data", courseID=courseID)
    # courseName = courses[0][1]
    # print(courses)
    if courses == False: #raise exception
        abort(404)
    #create variable to store these values
    teacherID = courses[1]
    courseName = courses[2]
    courseDescription = markdown.markdown(courses[3])
    coursePrice = courses[5]
    courseCategory = courses[6]
    courseRating = courses[7]
    courseRatingCount = courses[8]
    courseDate = courses[9]
    courseVideoPath = courses[10]

    print("course",courses[1])

    teacherProfilePath = get_image_path(teacherID)
    teacherRecords = sql_operation(table="user", mode="get_user_data", userID=teacherID, )
    print(teacherRecords)
    teacherName = teacherRecords[2]

    retrieveReviews = sql_operation(table="review", mode="retrieve_all" , courseID=courseID)
    print("the reviews", retrieveReviews)
    reviewList = []
    for i in retrieveReviews:
        reviewUserId = i[0]
        reviewCourseId = courseID 
        reviewRating = i[2]
        reviewComment = i[3]
        reviewDate = i[4]
        reviewUserName = i[5]
        reviewList.append(Reviews(reviewUserId, reviewCourseId, reviewRating, reviewComment, reviewDate, reviewUserName))
        
    print(reviewList[0].course_id)

    accType = imageSrcPath = None
    userPurchasedCourses = {}
    if ("user" in session):
        imageSrcPath, userInfo = get_image_path(session["user"], returnUserInfo=True)
        userPurchasedCourses = userInfo[-1]
        accType = userInfo[1]

    return render_template(
        "users/general/course_page.html",
        imageSrcPath=imageSrcPath, userPurchasedCourses=userPurchasedCourses, teacherName=teacherName, teacherProfilePath=teacherProfilePath \
        , courseID=courseID, courseName=courseName, courseDescription=courseDescription, coursePrice=coursePrice, courseCategory=courseCategory, \
        courseRating=courseRating, courseRatingCount=courseRatingCount, courseDate=courseDate, courseVideoPath=courseVideoPath, accType=accType,\
        reviewList= reviewList
    )

@generalBP.route("/search")
def search():
    """
    Search for courses

    E.g. of a search query:
    /search?q=DSA&p=2 # page 1 will not have any p argument but can have p=1 argument

    One good example is GitHub's search, notice how the url works.
    E.g. 
    - https://github.com/search?q=test&type=Repositories
    - https://github.com/search?p=2&q=test&type=Repositories
    
    TODO: Must handle all sorts of situation such as manually tampering with the url
    """
    searchInput = request.args.get("q", default="Courses", type=str)
    if (len(searchInput) > 100):
        abort(413)

    page = request.args.get("p", default=1, type=int)

    eachPageResults = []
    dictOfResults = {}
    pageNum = 1
    foundResults = sql_operation(table="course", mode="search", searchInput=searchInput)
    
    """
    Validates if any results are found to not induce a key errror
    """
    if (len(foundResults) != 0):
        """
        To seperate the results into to lists of 10.
        Stores the lists in a dictionary where the key is the Page of where the results should be displayed
        """
        for i in foundResults:
            if (len(eachPageResults)!=10):
                eachPageResults.append(i)
                dictOfResults[pageNum] = eachPageResults
            else:
                dictOfResults[pageNum] = eachPageResults
                eachPageResults = [i]
                pageNum += 1
        
        """
        To find the greatese page the pagination can extend to
        To help in validation
        """
        maxPage = max(list(dictOfResults))
        if (page > maxPage):
            abort(404)

        accType = imageSrcPath = None
        if ("user" in session):
            imageSrcPath, userInfo = get_image_path(session["user"], returnUserInfo=True)
            return render_template("users/general/search.html", searchInput=searchInput, foundResults=dictOfResults[page], foundResultsLen=len(foundResults), imageSrcPath=imageSrcPath, lenOfDict=dictOfResults, maxPage=maxPage, accType=userInfo[1])

        return render_template("users/general/search.html", searchInput=searchInput, currentPage=page, foundResults=dictOfResults[page], foundResultsLen=len(foundResults), lenOfDict=dictOfResults, maxPage=maxPage, accType=accType)
    
    accType = imageSrcPath = None
    if ("user" in session):
        imageSrcPath, userInfo = get_image_path(session["user"], returnUserInfo=True)
        return render_template("users/general/search.html", searchInput=searchInput, foundResults=dictOfResults, foundResultsLen=len(foundResults), imageSrcPath=imageSrcPath, lenOfDict=dictOfResults, accType=userInfo[1])

    return render_template("users/general/search.html", searchInput=searchInput, currentPage=page, foundResults=dictOfResults, foundResultsLen=len(foundResults), lenOfDict=dictOfResults, accType=accType)