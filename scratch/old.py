import cv2
import numpy as np

def make_photo_look_old(image_path, output_path):
    # 1. Load the image
    img = cv2.imread(image_path)
    if img is None:
        print("Error: Could not open or find the image.")
        return

    # 2. Apply a Sepia Matrix Transformation
    # OpenCV uses BGR format, so the matrix corresponds to Blue, Green, Red transformations
    sepia_matrix = np.array([[0.272, 0.534, 0.131],
                             [0.349, 0.686, 0.168],
                             [0.393, 0.769, 0.189]])
    
    # cv2.transform applies the matrix to every pixel
    sepia_img = cv2.transform(img, sepia_matrix)
    
    # Clip values to ensure they stay within valid 0-255 pixel range
    sepia_img = np.clip(sepia_img, 0, 255).astype(np.uint8)

    # 3. Generate and Add Film Grain (Noise)
    row, col, ch = sepia_img.shape
    # Create random Gaussian noise (mean=0, sigma=15)
    mean = 0
    sigma = 25
    gauss = np.random.normal(mean, sigma, (row, col, ch))
    
    # Add the noise to the sepia image
    noisy_img = sepia_img + gauss
    old_photo = np.clip(noisy_img, 0, 255).astype(np.uint8)

    # 4. Save the processed image
    cv2.imwrite(output_path, old_photo)
    print(f"Success! Vintage photo saved to {output_path}")

# Run the function
make_photo_look_old('../demo_inputs/IMG_3738.jpg', 'output.jpg')
