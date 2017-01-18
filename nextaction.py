#!/usr/bin/env python

import logging
import argparse

# noinspection PyPackageRequirements
from todoist.api import TodoistAPI

import time
import sys
from datetime import datetime


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
    parser.add_argument('-d', '--delay', help='Specify the delay in seconds between syncs', default=5, type=int)
    parser.add_argument('--debug', help='Enable debugging', action='store_true')
    parser.add_argument('--inbox', help='The method the Inbox project should be processed',
                        default='parallel', choices=['parallel', 'serial', 'none'])
    parser.add_argument('--parallel_suffix', default='.')
    parser.add_argument('--serial_suffix', default='_')
    parser.add_argument('--hide_future', help='Hide future dated next actions until the specified number of days',
                        default=7, type=int)
    parser.add_argument('--hide_scheduled', help='', action='store_true')  # TODO: help
    parser.add_argument('--remove_label', help='Remove next action label from unmarked projects', action='store_true')
    parser.add_argument('--onetime', help='Update Todoist once and exit', action='store_true')
    parser.add_argument('--nocache', help='Disables caching data to disk for quicker syncing', action='store_true')
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

    api_arguments = {'token': args.api_key}
    if args.nocache:
        logging.debug('Disabling local caching')
        api_arguments['cache'] = None

    api = TodoistAPI(**api_arguments)
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

    def get_project_type(project_object):
        """Identifies how a project should be handled."""
        name = project_object['name'].strip()
        if name == 'Inbox' and args.inbox != 'none':
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

    def add_label(item, label):
        if label not in item['labels']:
            logging.debug('Updating %s (%d) with label', item['content'], item['id'])
            labels = item['labels']
            labels.append(label)
            api.items.update(item['id'], labels=labels)

    def remove_label(item, label):
        if label in item['labels']:
            logging.debug('Updating %s (%d) without label', item['content'], item['id'])
            labels = item['labels']
            labels.remove(label)
            api.items.update(item['id'], labels=labels)

    # Main loop
    while True:
        try:
            api.sync()
        except Exception as e:
            logging.exception('Error trying to sync with Todoist API: %s' % str(e))
        else:
            for project in api.projects.all(lambda x: not x['is_deleted'] and not x['is_archived']):
                project_type = get_project_type(project)
                items = api.items.all(
                            lambda x: x['project_id'] == project['id']
                                      and not (x['checked'] or x['is_deleted'] or x['is_archived'])
                )
                if project_type:
                    logging.debug('Project %s being processed as %s', project['name'], project_type)

                    # Get all items for the project, sort by the item_order field.
                    items = sorted(
                        items,
                        key=lambda x: x['item_order']
                    )

                    for real_order, item in enumerate(filter(lambda x: x['indent'] == 1, items)):
                        item_type = get_item_type(item)

                        if item.data.get('due_date_utc'):
                            if args.hide_scheduled and not item_type:
                                remove_label(item, label_id)
                                continue

                            # If its too far in the future, remove the next_action tag and skip
                            if args.hide_future > 0:
                                due_date = datetime.strptime(item['due_date_utc'], '%a %d %b %Y %H:%M:%S +0000')
                                future_diff = (due_date - datetime.utcnow()).total_seconds()
                                if future_diff >= (args.hide_future * 86400):
                                    remove_label(item, label_id)
                                    continue

                        child_items = get_subitems(items, item)

                        def add_indent1_label():
                            if child_items:
                                remove_label(item, label_id)
                                add_label(child_items[0], label_id)
                                func = remove_label if item_type == 'serial' else add_label
                                for child_item in child_items[1:]:
                                    func(child_item, label_id)
                            else:
                                add_label(item, label_id)

                        def remove_indent1_label():
                            remove_label(item, label_id)
                            for child_item in child_items:
                                remove_label(child_item, label_id)

                        if project_type == 'serial':
                            if real_order == 0:
                                add_indent1_label()
                            else:
                                remove_indent1_label()
                        elif project_type == 'parallel':
                            add_indent1_label()

                elif args.remove_label:
                    for item in items:
                        remove_label(item, label_id)

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
