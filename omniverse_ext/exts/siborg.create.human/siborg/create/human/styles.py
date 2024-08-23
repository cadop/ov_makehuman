# Stylesheet for parameter panels
panel_style = {
    "Rectangle::group_rect": {
        "background_color": 0xFF313333,
        "border_radius": 5,
        "margin": 5,
    },
    "VStack::contents": {
        "margin": 10,
    },
}

# Stylesheet for sliderentry widgets
sliderentry_style = {
    "Label::label_param": {
        "margin_width": 10,
    },
}

# stylesheet for collapseable frame widgets, used for each modifier category
frame_style = {
    "CollapsableFrame": {
        "background_color": 0xFF1F2123,
    },
}

# stylesheet for main UI window
window_style = {
    "Rectangle::splitter": {"background_color": 0xFF454545},
    "Rectangle::splitter:hovered": {"background_color": 0xFFFFCA83},
}

# Stylesheet for buttons
button_style = {
    "Button:disabled": {
        "background_color": 0xFF424242,
    },
    "Button:disabled.Label": {
        "color": 0xFF848484,
    },
}
