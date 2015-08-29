from distutils.core import setup

setup(
    name='NextAction',
    version='0.1',
    py_modules=['nextaction'],
    url='https://github.com/nikdoof/NextAction',
    license='MIT',
    author='Andrew Williams',
    author_email='andy@tensixtyone.com',
    description='A more GTD-like workflow for Todoist. Uses the REST API to add and remove a @next_action label from tasks.',
    entry_points={
        "distutils.commands": [
            "nextaction = nextaction:main",
            ],
        }
)
