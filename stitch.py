from moviepy.editor import VideoFileClip, concatenate_videoclips
import os

folder = r"C:\Users\user\Documents\DirectorX\temp\The_Tiny_Problem_Solver_Toddler_Logic"

# Teeno parts load kar rahe hain
clip1 = VideoFileClip(os.path.join(folder, "dx_The_Tiny_Problem_Solver_Toddler_Logic_s00_twopass.mp4"))
clip2 = VideoFileClip(os.path.join(folder, "dx_The_Tiny_Problem_Solver_Toddler_Logic_s01_twopass.mp4"))
clip3 = VideoFileClip(os.path.join(folder, "dx_The_Tiny_Problem_Solver_Toddler_Logic_s02_twopass.mp4"))

# Clips ko ek sath jod rahe hain
final_clip = concatenate_videoclips([clip1, clip2, clip3])

# Final video save kar rahe hain
output_path = os.path.join(folder, "FINAL_REEL_COMBINED.mp4")
final_clip.write_videofile(output_path, codec="libx264")
print(f"Aapki final video yahan save ho gayi hai: {output_path}")