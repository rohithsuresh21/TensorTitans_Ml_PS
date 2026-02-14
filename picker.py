import cv2

video_path = r"C:\Users\Rohith M S\OneDrive\Desktop\projects\Hackathon\theft.mp4"
points = []

def click_event(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN:  
        cv2.circle(img, (x,y), 5, (0, 0, 255), -1)  
        points.append((x, y))  
        print(f"Selected point: ({x}, {y})")  

        if len(points) > 1:
            cv2.line(img, points[-2], points[-1], (255, 0, 0), 2)

        cv2.imshow("coordinates", img) 

cap = cv2.VideoCapture(video_path)
success, img = cap.read()

if not success:
    print("Failed to load video :(")
else:
    cv2.namedWindow("coordinates") 
    
    # --- THIS WAS THE MISSING LINE ---
    cv2.setMouseCallback("coordinates", click_event) 

    print("1. Click the corners of restricted zone in order.")
    print("2. Press 'q' or any key to finish and get coordinates.")

    # Keep the window open and responsive
    while True:
        cv2.imshow("coordinates", img)
        if cv2.waitKey(1) & 0xFF == ord('q'): # Press 'q' to exit
            break
            
    cv2.destroyAllWindows()  
    print("The final list of selected points is:", points)