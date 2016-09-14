#!/usr/bin/env python

import logging
import argparse

# noinspection PyPackageRequirements
from todoist.api import TodoistAPI

import time
import sys
from datetime import datetime


class Found(Exception):
    pass


def get_subitems(items, parent_item=None):
    """Search a flat item list for child items."""
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


def main():
    """Main process function."""
    parser = argparse.ArgumentParser()
    parser.add_argument('-a', '--api_key', help='Todoist API Key')
    parser.add_argument('-l', '--label', help='The next action label to use', default='next_action')
    parser.add_argument('--everywhere_label', help='The *everywhere label to use', default='')
    parser.add_argument('-d', '--delay', help='Specify the delay in seconds between syncs', default=5, type=int)
    parser.add_argument('--debug', help='Enable debugging', action='store_true')
    parser.add_argument('--inbox', help='The method the Inbox project should be processed',
                        default='parallel', choices=['parallel', 'serial', 'none'])
    parser.add_argument('--priority', default=1, type=int)
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
    logging.debug('Syncing the current state from the API')
    api.sync()

    # Check the next action label exists
    labels = api.labels.all(lambda x: x['name'] == args.label)
    if len(labels) > 0:
        label_id = labels[0]['id']
        logging.debug('Label %s found as label id %d', args.label, label_id)
    else:
        logging.error("Label %s doesn't exist, please create it or change TODOIST_NEXT_ACTION_LABEL.", args.label)
        sys.exit(1)

    # Check the everywhere label exists
    everywhere_labels = api.labels.all(lambda x: x['name'] == args.everywhere_label)
    everywhere_label_id = -1
    if len(everywhere_labels) > 0:
        everywhere_label_id = everywhere_labels[0]['id']
        logging.debug('Everywhere label %s found as label id %d', args.everywhere_label, everywhere_label_id)

    # Get location labels
    location_labels = api.labels.all(lambda x: x['name'][0] == '*' and x['id'] != everywhere_label_id)
    location_labels_ids = set(d['id'] for d in location_labels)
    logging.debug("location_labels: " + ', '.join(map(str, location_labels_ids)))

    def get_project_type(project_object):
        """Identifies how a project should be handled."""
        name = project_object['name'].strip()
        if project['name'] == 'Inbox' and args.inbox != 'none':
            return args.inbox
        elif name[-1] == args.parallel_suffix:
            return 'parallel'
        elif name[-1] == args.serial_suffix:
            return 'serial'

    def get_item_type(item):
        """Identifies how a item with sub items should be handled."""
        name = item['content'].strip()
        if name[-1] == args.parallel_suffix:
            return 'parallel'
        elif name[-1] == args.serial_suffix:
            return 'serial'

    def set_priority(item, priority):
        if item['priority'] != priority:
            api.items.update(item['id'], priority=priority)

    def add_label(item, label):
        if label not in item['labels']:
            labels = item['labels']
            logging.debug('Updating %s with label %d', item['content'], label)
            labels.append(label)
            api.items.update(item['id'], labels=labels)

    def remove_label(item, label):
        if label in item['labels']:
            labels = item['labels']
            logging.debug('Updating %s without label %d', item['content'], label)
            labels.remove(label)
            api.items.update(item['id'], labels=labels)

    def add_next_action_label(item):
        add_label(item, label_id)
        set_priority(item, args.priority)

    def remove_next_action_label(item):
        remove_label(item, label_id)
        set_priority(item, 1)

    def set_location_labels(item):
        if everywhere_label_id >= 0:
            labels_ids = set(item['labels'])
            if labels_ids & location_labels_ids:
                remove_label(item, everywhere_label_id)
            else:
                add_label(item, everywhere_label_id)
            # try:
            #     for label_id in labels_ids:
            #         if label_id in location_labels_ids:
            #             logging.debug("FOUND!!!")
            #             raise Found
            #     logging.debug("NOT FOUND!!!")
            #     add_label(item, everywhere_label_id)
            # except Found:
            #     remove_label(item, everywhere_label_id)

    # Main loop
    while True:
        try:
            api.sync()
        except Exception as e:
            logging.exception('Error trying to sync with Todoist API: %s' % str(e))
        else:
            for project in api.projects.all():
                project_type = get_project_type(project)
                items = api.items.all(lambda x: x['project_id'] == project['id'] and not x['checked'])
                if project_type:
                    logging.debug('Project %s being processed as %s', project['name'], project_type)

                    # Get all unchecked items for the project, sort by the item_order field.
                    items = sorted(items, key=lambda x: x['item_order'])

                    for item in items:
                        set_location_labels(item)
                        # If its too far in the future, remove the next_action tag and skip
                        if args.hide_future > 0 and 'due_date_utc' in item.data and item['due_date_utc'] is not None:
                            due_date = datetime.strptime(item['due_date_utc'], '%a %d %b %Y %H:%M:%S +0000')
                            future_diff = (due_date - datetime.utcnow()).total_seconds()
                            if future_diff >= (args.hide_future * 86400):
                                remove_next_action_label(item)
                                continue

                        item_type = get_item_type(item)
                        child_items = get_subitems(items, item)
                        #if item_type:
                        logging.debug('Identified %s as %s type', item['content'], item_type)

                        if item_type or len(child_items) > 0:
                            # Process serial tagged items
                            if item_type == 'serial':
                                for idx, child_item in enumerate(child_items):
                                    if idx == 0:
                                        add_next_action_label(child_item)
                                    else:
                                        remove_next_action_label(child_item)
                            # Process parallel tagged items or untagged parents
                            else:
                                for child_item in child_items:
                                    add_next_action_label(child_item)

                            # Remove the label from the parent
                            remove_next_action_label(item)

                        # Process items as per project type on indent 1 if untagged
                        else:
                            if item['indent'] == 1:  # top level
                                if project_type == 'serial':
                                    if item['item_order'] == 1:
                                        add_next_action_label(item)
                                    else:
                                        remove_next_action_label(item)
                                elif project_type == 'parallel':
                                    add_next_action_label(item)
                # remove labels from items in unprocessed projects
                else:
                    logging.debug('Project %s being processed as None', project['name'])
                    for item in items:
                        set_location_labels(item)
                        remove_next_action_label(item)

            if len(api.queue):
                logging.debug('%d changes queued for sync... commiting to Todoist.', len(api.queue))
                api.commit()
            else:
                logging.debug('No changes queued, skipping sync.')

        # If onetime is set, exit after first execution.
        if args.onetime:
            break

        logging.debug('Sleeping for %d seconds', args.delay)
        time.sleep(args.delay)


if __name__ == '__main__':
    main()
