#!/usr/bin/env python

import logging
import argparse

# noinspection PyPackageRequirements
from todoist.api import TodoistAPI

import time
import sys
from datetime import datetime

class TodoistConnection(object):
    """docstring for TodoistConnection"""
    def __init__(self, args, api, logging):
        super(TodoistConnection, self).__init__()
        self.args = args
        self.api = api
        self.logging = logging
        self.label = None
        
    def get_subitems(self, items, parent_item=None):
        """Search a flat item list for child items"""
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
                elif item['indent'] == required_indent and found:
                    result_items.append(item)
            elif item['indent'] == required_indent:
                result_items.append(item)
        return result_items

    def get_project_type(self, project_object):
        """Identifies how a project should be handled"""
        name = project_object['name'].strip()
        if name == 'Inbox':
            return self.args.inbox
        elif name[-1] == self.args.parallel_suffix:
            return 'parallel'
        elif name[-1] == self.args.serial_suffix:
            return 'serial'

    def get_item_type(self, item):
        """Identifies how a item with sub items should be handled"""
        name = item['content'].strip()
        if name[-1] == self.args.parallel_suffix:
            return 'parallel'
        elif name[-1] == self.args.serial_suffix:
            return 'serial'

    def add_label(self, item):
        if self.label not in item['labels']:
            labels = item['labels']
            self.logging.debug('Updating %s with label', item['content'])
            labels.append(self.label)
            self.api.items.update(item['id'], labels=labels)

    def remove_label(self, item):
        if self.label in item['labels']:
            labels = item['labels']
            self.logging.debug('Updating %s without label', item['content'])
            labels.remove(self.label)
            self.api.items.update(item['id'], labels=labels)

    # Main loop

def main():

    parser = argparse.ArgumentParser()
    parser.add_argument('-a', '--api_key', help='Todoist API Key')
    parser.add_argument('-l', '--label', help='The next action label to use', default='next_action')
    parser.add_argument('-d', '--delay', help='Specify the delay in seconds between syncs', default=5, type=int)
    parser.add_argument('--debug', help='Enable debugging', action='store_true')
    parser.add_argument('--inbox', help='The method the Inbox project should be processed',
                        default='parallel', choices=['parallel', 'serial'])
    parser.add_argument('--parallel_suffix', default='.')
    parser.add_argument('--serial_suffix', default='_')
    parser.add_argument('--hide_future', help='Hide future dated next actions until the specified number of days',
                        default=7, type=int)
    parser.add_argument('--onetime', help='Update Todoist once and exit', action='store_true')
    args = parser.parse_args()

    # Set debug
    if args.debug:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO
    logging.basicConfig(level=log_level)

    # Check we have a API key
    if not args.api_key:
        logging.error('No API key set, exiting...')
        sys.exit(1)

    # Run the initial sync
    logging.debug('Connecting to the Todoist API')
    api = TodoistAPI(token=args.api_key)
    conn = TodoistConnection(args, api, logging)

    conn.logging.debug('Syncing the current state from the API')
    conn.api.sync(resource_types=['projects', 'labels', 'items'])

    # Check the next action label exists
    labels = conn.api.labels.all(lambda x: x['name'] == args.label)
    if len(labels) > 0:
        label_id = labels[0]['id']
        conn.logging.debug('Label %s found as label id %d', args.label, label_id)
    else:
        conn.logging.error("Label %s doesn't exist, please create it or change TODOIST_NEXT_ACTION_LABEL.", args.label)
        sys.exit(1)

    conn.label = label_id

    while True:
        try:
            conn.api.sync(resource_types=['projects', 'labels', 'items'])
        except Exception as e:
            conn.logging.exception('Error trying to sync with Todoist API: %s' % str(e))
        else:
            for project in conn.api.projects.all():
                project_type = conn.get_project_type(project)
                if project_type:
                    conn.logging.debug('Project %s being processed as %s', project['name'], project_type)

                    items = sorted(conn.api.items.all(lambda x: x['project_id'] == project['id']), key=lambda x: x['item_order'])

                    for item in items:

                        # If its too far in the future, remove the next_action tag and skip
                        if conn.args.hide_future > 0 and 'due_date_utc' in item.data and item['due_date_utc'] is not None:
                            due_date = datetime.strptime(item['due_date_utc'], '%a %d %b %Y %H:%M:%S +0000')
                            future_diff = (due_date - datetime.utcnow()).total_seconds()
                            if future_diff >= (conn.args.hide_future * 86400):
                                conn.remove_label(item)
                                continue

                        item_type = conn.get_item_type(item)
                        child_items = conn.get_subitems(items, item)
                        if item_type:
                            conn.logging.debug('Identified %s as %s type', item['content'], item_type)

                        if item_type or len(child_items) > 0:
                            # Process serial tagged items
                            if item_type == 'serial':
                                for idx, child_item in enumerate(child_items):
                                    if idx == 0:
                                        conn.add_label(child_item)
                                    else:
                                        conn.remove_label(child_item)
                            # Process parallel tagged items or untagged parents
                            else:
                                for child_item in child_items:
                                    conn.add_label(child_item)

                            # Remove the label from the parent
                            conn.remove_label(item)

                        # Process items as per project type on indent 1 if untagged
                        else:
                            if item['indent'] == 1:
                                if project_type == 'serial':
                                    if item['item_order'] == 1:
                                        conn.add_label(item)
                                    else:
                                        conn.remove_label(item)
                                elif project_type == 'parallel':
                                    conn.add_label(item)

            conn.logging.debug('%d changes queued for sync... commiting if needed', len(conn.api.queue))
            if len(conn.api.queue):
                conn.api.commit()

        if conn.args.onetime:
            break
        conn.logging.debug('Sleeping for %d seconds', conn.args.delay)
        time.sleep(conn.args.delay)


if __name__ == '__main__':
    main()
