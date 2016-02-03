NextAction
==========

A more GTD-like workflow for Todoist. Uses the REST API to add and remove a `@next_action` label from tasks.

This program looks at every list in your Todoist account.
Any list that ends with `_` or `.` is treated specially, and processed by NextAction.

Note that NextAction requires Todoist Premium to function properly, as labels are a premium feature.

Requirements
============

* Python 2.7, Python 3.0+ is unsupported at the moment
* ```todoist-python``` package.

Activating NextAction
=====================

Sequential list processing
--------------------------
If a project or task ends with `_`, the child tasks will be treated as a priority queue and the most important will be labeled `@next_action`.
Importance is determined by order in the list

Parallel list processing
------------------------
If a project or task name ends with `.`, the child tasks will be treated as parallel `@next_action`s.
The waterfall processing will be applied the same way as sequential lists - every parent task will be treated as sequential. This can be overridden by appending `_` to the name of the parent task.

Executing NextAction
====================

You can run NexAction from any system that supports Python.

Running NextAction
------------------

NextAction will read your environment to retrieve your Todoist API key, so to run on a Linux/Mac OSX you can use the following commandline

    python nextaction.py -a <API Key>
