# Human Generator API Example
# Author: Joshua Grebler | SiBORG Lab | 2023
# Description: This is an example of how to use the Human Generator API to create human models in NVIDIA Omniverse.
# The siborg.create.human extension must be installed and enabled for this to work.

# The script generates 10 humans, placing them throughout the stage. Random modifiers and clothing are applied to each.

import siborg.create.human as hg
from siborg.create.human.shared import data_path
import omni.usd
import random

# Get the stage
context = omni.usd.get_context()
stage = context.get_stage()

# Make a single Human to start with
human = hg.Human()
human.add_to_scene()

# Apply a modifier by name (you can find the names of all the available modifiers
# by using the `get_modifier_names()` method)
height = human.get_modifier_by_name("macrodetails-height/Height")
human.set_modifier_value(height, 1)
# Update the human in the scene
human.update_in_scene(human.prim_path)

# Gather some default clothing items (additional clothing can be downloaded from the extension UI)
clothes = ["nvidia_Casual/nvidia_casual.mhclo", "omni_casual/omni_casual.mhclo", "siborg_casual/siborg_casual.mhclo"]

# Convert the clothing names to their full paths.
clothes = [data_path(f"clothes/{c}") for c in clothes]

# Create 20 humans, placing them randomly throughout the scene, and applying random modifier values
for _ in range(10):
    h = hg.Human()
    h.add_to_scene()

    # Apply a random translation and Y rotation to the human prim
    translateOp = h.prim.AddTranslateOp()
    translateOp.Set((random.uniform(-50, 50), 0, random.uniform(-50, 50)))
    rotateOp = h.prim.AddRotateXYZOp()
    rotateOp.Set((0, random.uniform(0, 360), 0))

    # Apply a random value to the last 9 modifiers in the list.
    # These modifiers are macros that affect the overall shape of the human more than any individual modifier.

    # Get the last 9 modifiers
    modifiers = h.get_modifiers()[-9:]

    # Apply a random value to each modifier. Use the modifier's min/max values to ensure the value is within range.

    for m in modifiers:
        h.set_modifier_value(m, random.uniform(m.getMin(), m.getMax()))


    # Update the human in the scene
    h.update_in_scene(h.prim_path)

    # Add a random clothing item to the human
    h.add_item(random.choice(clothes))
