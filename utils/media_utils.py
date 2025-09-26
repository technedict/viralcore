from telegram import InputMediaPhoto, InputFile

# -------------------------------
# Helper function to return InputMediaPhoto properly.
# -------------------------------
def get_media(image_ref, caption):
    if image_ref is None:
        return None
    if image_ref.startswith("http"):
        return InputMediaPhoto(media=image_ref, caption=caption)
    else:
        return InputMediaPhoto(media=InputFile(image_ref), caption=caption)