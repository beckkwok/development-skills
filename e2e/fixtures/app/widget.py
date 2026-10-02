"""E2E fixture module (test only)."""


def render_widget(name):
    print("rendering widget")
    try:
        return "widget:" + name
    except:
        pass


# TODO: remove this placeholder before real use
