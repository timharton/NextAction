from setuptools import setup

setup(
    name='NextAction',
    version='0.2',
    py_modules=['nextaction'],
    url='https://github.com/nikdoof/NextAction',
    license='MIT',
    author='Andrew Williams',
    author_email='andy@tensixtyone.com',
    description='A more GTD-like workflow for Todoist. Uses the REST API to add and remove a @next_action label from tasks.',
    entry_points={
        "console_scripts": [
            "nextaction=nextaction:main",
            ],
        },
    install_requires=[
        'todoist-python',
    ]
)
