import sys
import pyparsing
import re
import subprocess
import os
import time


def paths_from_srv():
    output = cmd_get_result(f'sc query')
    if output is None:
        raise Exception('Error')
    ru = output.find('Имя_службы') > -1
    if ru:
        pattern = "Имя_службы: (1C:.+)"
    else:
        pattern = "SERVICE_NAME: (1C:.+)"

    data_services = list()

    all_find = re.findall(pattern, output)
    for finded in all_find:
        output = cmd_get_result(f'sc qc "{finded[:-1]}"')
        if ru:
            pattern = 'Имя_двоичного_файла.+ -regport ([\d]+).+-port ([\d]+) .+-d "(.+)"'
        else:
            pattern = 'BINARY_PATH_NAME.+ -regport ([\d]+).+-port ([\d]+) .+-d "(.+)"'

        re_data = re.findall(pattern, output)
        if len(re_data) == 0:
            continue
        all_data = re_data[0]
        regport = all_data[0]
        port = all_data[1]
        srvinfo_path = all_data[2]
        mod_srvinfo_path = f'{srvinfo_path[:1]}:{srvinfo_path[2:]}{os.sep}reg_{regport}{os.sep}1CV8Clst.lst'

        data_services.append({
            'port': regport,
            'srvinfo_path': srvinfo_path,
            'path_to_lst': mod_srvinfo_path,
            'svc_name': finded
        })

    return data_services


def cmd_get_result(cmd):
    try:
        output = subprocess.check_output(cmd)
        decoded_output = output.decode('CP866')
        return decoded_output
    except Exception as e:
        return None


def get_text_from_path(path):
    with open(path, 'r', encoding='utf-8') as file:
        return file.read()


def write_text_to_file(text, path):
    with open(path, 'w', encoding='utf-8') as file:
        file.write(text)


def unbox_stings(element, result):
    for i in element:
        if type(i) == list:
            string = ''
            unbox_stings(i, result)
        else:
            string = i
        result += string


def get_info_from_lst(path):

    text_from_file = get_text_from_path(path).replace('﻿', '')

    data = pyparsing.nestedExpr('{', '}').parseString(text_from_file).asList()

    return data


def pending_start_stop_svc(name, pending_state):
    while True:
        stdout = cmd_get_result(f'sc query "{name}"')
        if stdout.find('Имя_службы') != -1:
            pattern = 'Состояние {0,100}: (\d+)'
        else:
            pattern = 'STATE {0,100}: (\d+)'

        finded = re.findall(pattern, stdout)
        if len(finded) == 0:
            print('Произошла ошибка при ожидании переключения состояния службы. Проверьте состояние службы вручную.')
            sys.exit()

        current_state = int(finded[0])

        if current_state != pending_state:
            time.sleep(5)
        else:
            break


def stop_svc(name):
    cmd_get_result(f'sc stop "{name}"')
    pending_start_stop_svc(name, 1)


def start_svc(name):
    cmd_get_result(f'sc start "{name}"')
    pending_start_stop_svc(name, 4)


def add_user(data, user, pwd):
    # user block #7
    users_data = data[0][7]

    count_users = users_data[0]

    count_users = int(count_users[0:-1]) if count_users[-1:] == ',' else int(count_users)

    if int(count_users) > 0:
        # Check doubles
        for cur_user in users_data:
            if f'"{user}"' in cur_user:
                return f'Пользователь [{user}] уже присутствует в данном кластере.'
    # else:
    #     return f'В консоли кластера нет ни одного зарегистрированного пользователя. Регистрируйте руками)'

    users_data[0] = str(count_users + 1) + ',' if count_users > 0 else str(count_users + 1)
    users_data.append(',')
    users_data.append(list((f'"{user}"', ',', '""', ',', '""', ',', f'"{pwd}"', ',', '""', ',1')))

    data[0][7] = users_data

    return ''


def save_changes(data, path):
    nested_data = str(data[0]).replace('[', '{').replace(']', '}').replace("'", '').replace(',,', ',') \
        .replace(', ,', ',').replace(', ', ',').replace('\\\\', '\\')

    write_text_to_file(nested_data, path)


def main():

    print('''
===============================================================================================
| Программа позволяет добавить администратора кластера 1C с введенным именем и паролем = "1"  |
===============================================================================================
|                  Программа должна быть запущена от имени администратора !!!                 |
===============================================================================================\n''')

    all_paths = paths_from_srv()
    if len(all_paths) > 1:
        print('Найдено больше одной запущенной службы 1С:')
        for srv in all_paths:
            index = all_paths.index(srv) + 1
            print(f'[{index}] Port: {srv["port"]}. Path: {srv["path_to_lst"]}')

        choice = input('Выберите версию вводом числа ->')

        while True:

            if re.match('[\d]+', choice) == None:
                choice = input('Некорректный ввод. Введите число ->')
                continue

            if int(choice) > len(all_paths) or int(choice) < len(all_paths):
                choice = input('Введено число меньше\больше общего количества доступных элементов. Введите число ->')
                continue

            break

        choice_int = int(choice)
        choice_int -= 1

    elif len(all_paths) == 0:
        input('Не обнаружено запущенных серверов 1С. Нажмите ENTER для выхода из программы.')
        sys.exit()
    else:
        choice_int = 0

    path = all_paths[choice_int]['path_to_lst']

    svc_name = all_paths[choice_int]["svc_name"].replace('\r', '')

    print(f'Имя выбранного сервиса: [{svc_name}]. Порт кластера: [{all_paths[choice_int]["port"]}]\n')

    user = input('Введите имя пользователя -> ')
    pwd = 'NWoZK3kTsExUV00Ywo1G5jlUKKs=' # 1

    data = get_info_from_lst(path)
    err = add_user(data, user, pwd)

    if err == '':
        save_changes(data, path)
        print(f'Пользователь [{user}] с паролем [1] добавлен в кластер\n')

        choice = input(f'Перезапустить службу сервера [{svc_name}]? (y\\n) -> ')
        if choice == 'y':
            print('     Остановка службы...')
            stop_svc(svc_name)
            print('     Запуск службы...')
            start_svc(svc_name)
            print('Запущено.\n')

    else:
        print(err)

    input('Для выхода нажмите ENTER')


if __name__ == '__main__':
    main()
