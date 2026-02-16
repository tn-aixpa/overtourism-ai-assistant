from PIL import Image, ImageDraw, ImageFont


def draw_conversation(messages, im_name):

    # ---------- SETTINGS ----------
    WIDTH = 900
    PADDING = 20
    BUBBLE_PADDING = 15
    MAX_BUBBLE_WIDTH = int(WIDTH * 0.65)

    BG_COLOR = (245, 245, 245)
    USER_COLOR = (0, 132, 255)
    ASSISTANT_COLOR = (230, 230, 230)
    TEXT_COLOR_USER = (255, 255, 255)
    TEXT_COLOR_ASSISTANT = (0, 0, 0)

    font = ImageFont.load_default()

    # ---------- HELPERS ----------

    def text_size(draw, text):
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]

    def wrap_text_pixels(draw, text, max_width):
        """Wrap text based on rendered pixel width."""
        lines = []

        for paragraph in str(text).split("\n"):

            if paragraph.strip() == "":
                lines.append("")
                continue

            words = paragraph.split(" ")
            current_line = ""

            for word in words:

                test_line = current_line + (" " if current_line else "") + word
                w, _ = text_size(draw, test_line)

                if w <= max_width:
                    current_line = test_line
                else:
                    if current_line:
                        lines.append(current_line)
                    current_line = word

            lines.append(current_line)

        return lines

    # ---------- FIRST PASS (measure height) ----------

    temp_img = Image.new("RGB", (WIDTH, 1000))
    temp_draw = ImageDraw.Draw(temp_img)

    rendered_messages = []
    total_height = PADDING

    for msg in messages:

        lines = wrap_text_pixels(
            temp_draw,
            msg["content"],
            MAX_BUBBLE_WIDTH - (BUBBLE_PADDING * 2)
        )

        # measure widest line
        max_line_width = 0
        line_height = text_size(temp_draw, "Ay")[1]

        for line in lines:
            w, _ = text_size(temp_draw, line)
            max_line_width = max(max_line_width, w)

        bubble_width = max_line_width + BUBBLE_PADDING * 2
        bubble_width = min(bubble_width, MAX_BUBBLE_WIDTH)

        bubble_height = len(lines) * line_height + BUBBLE_PADDING * 2

        rendered_messages.append((msg, lines, bubble_width, bubble_height))

        total_height += bubble_height + 15

    total_height += PADDING

    # ---------- CREATE FINAL IMAGE ----------

    img = Image.new("RGB", (WIDTH, total_height), BG_COLOR)
    draw = ImageDraw.Draw(img)

    y_offset = PADDING

    for msg, lines, bubble_width, bubble_height in rendered_messages:

        if msg["role"] == "user":
            x = WIDTH - bubble_width - PADDING
            bubble_color = USER_COLOR
            text_color = TEXT_COLOR_USER
        else:
            x = PADDING
            bubble_color = ASSISTANT_COLOR
            text_color = TEXT_COLOR_ASSISTANT

        draw.rounded_rectangle(
            (x, y_offset, x + bubble_width, y_offset + bubble_height),
            radius=20,
            fill=bubble_color,
        )

        text_y = y_offset + BUBBLE_PADDING
        line_height = text_size(draw, "Ay")[1]

        for line in lines:
            draw.text(
                (x + BUBBLE_PADDING, text_y),
                line,
                fill=text_color,
                font=font
            )
            text_y += line_height

        y_offset += bubble_height + 15

    img.save(im_name)
