#!/usr/bin/env python

import time
import logging
import os
import sys

from todoist.api import TodoistAPI


API_TOKEN = os.environ.get('TODOIST_API_KEY', None)
NEXT_ACTION_LABEL = os.environ.get('TODOIST_NEXT_ACTION_LABEL', 'next_action')
SYNC_DELAY = int(os.environ.get('TODOIST_SYNC_DELAY', '5'))
INBOX_HANDLING = os.environ.get('TODOIST_INBOX_HANDLING', 'parallel')
PARALLEL_SUFFIX = os.environ.get('TODOIST_PARALLEL_SUFFIX', '=')
SERIAL_SUFFIX = os.environ.get('TODOIST_SERIAL_SUFFIX', '-')

def get_project_type(project):
    """Identifies how a project should be handled"""
    name = project['name'].strip()
    if project['name'] == 'Inbox':
        return INBOX_HANDLING
    elif name[-1] == PARALLEL_SUFFIX:
        return 'parallel'
    elif name[-1] == SERIAL_SUFFIX:
        return 'serial'


def get_subitems(items, parent_item=None):
    result_items = []
    found = False
    if parent_item:
        required_indent = parent_item['indent'] + 1
    else:
        required_indent = 1
    for item in items:
        if parent_item:
            if not found and item['id'] != parent_item['id']:
                continue
            else:
                found = True
            if item['indent'] == parent_item['indent'] and item['id'] != parent_item['id']:
                return result_items
        elif item['indent'] == required_indent:
            result_items.append(item)
    return result_items


def main():
    if os.environ.get('TODOIST_DEBUG', None):
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO
    logging.basicConfig(level=log_level)
    if not API_TOKEN:
        logging.error('No API key set, exiting...')
        sys.exit(1)

    logging.debug('Connecting to the Todoist API')
    api = TodoistAPI(token=API_TOKEN)
    logging.debug('Syncing the current state from the API')
    api.sync(resource_types=['projects', 'labels', 'items'])

    labels = api.labels.all(lambda x: x['name'] == NEXT_ACTION_LABEL)
    if len(labels) > 0:
        label_id = labels[0]['id']
        logging.debug('Label %s found as label id %d', NEXT_ACTION_LABEL, label_id)
    else:
        logging.error("Label %s doesn't exist, please create it or change TODOIST_NEXT_ACTION_LABEL.", NEXT_ACTION_LABEL)
        sys.exit(1)

    while True:
        api.sync(resource_types=['projects', 'labels', 'items'])
        for project in api.projects.all():
            proj_type = get_project_type(project)
            if proj_type:
                logging.debug('Project %s being processed as %s', project['name'], proj_type)

                # Parallel
                if proj_type == 'parallel':
                    items = api.items.all(lambda x: x['project_id'] == project['id'])
                    for item in items:
                        labels = item['labels']
                        if label_id not in labels:
                            logging.debug('Updating %s with label', item['content'])
                            labels.append(label_id)
                            item.update(labels=labels)

                # Serial
                if proj_type == 'serial':
                    items = sorted(api.items.all(lambda x: x['project_id'] == project['id']), key=lambda x: x['item_order'])
                    for item in items:
                        labels = item['labels']
                        if item['item_order'] == 1:

                            if label_id not in labels:
                                labels.append(label_id)
                                logging.debug('Updating %s with label', item['content'])
                                item.update(labels=labels)
                        else:
                            if label_id in labels:
                                labels.remove(label_id)
                                logging.debug('Updating %s without label', item['content'])
                                item.update(labels=labels)

        api.sync(resource_types=['projects', 'labels', 'items'])
        logging.debug('Sleeping for %d seconds', SYNC_DELAY)
        time.sleep(SYNC_DELAY)


if __name__ == '__main__':
    main()
