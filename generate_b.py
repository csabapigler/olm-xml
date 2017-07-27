import sys
import re
import io
import pandas as pd
import pyodbc

# variables
NAMESPACE = 'HU.OMSZ.AQ'
CODE_COMB = 3
ZONE_STRING = '<aqd:content xlink:href="' + NAMESPACE + '/{zone_name}"/>'

GET_RESPONSIBLE_QUERY = "SELECT * FROM (AQD_responsible_authority ra " \
                        "INNER JOIN person p on p.ps_code = ra.ps_code) " \
                        "INNER JOIN organization o on o.og_code = ra.og_code " \
                        "WHERE ra.nn_code_iso2 = 'hu' AND ra.ac_code_comb = {code_comb}". \
    format(code_comb=CODE_COMB)

GET_POLLUTANT_QUERY = "SELECT * FROM AQD_zone_pollutant " \
                      "WHERE nn_code_iso2 = 'hu' " \
                      "AND zn_code = '{zn_code}'"

GET_ZONES_QUERY = "SELECT * FROM AQD_ZONE WHERE nn_code_iso2='hu';"


def init_connection(drv, mdb):

    conn_str = 'DRIVER={driver};DBQ={mdb_location}'
    return pyodbc.connect(conn_str.format(driver=drv, mdb_location=mdb))


def read_structure(filename):
    fhand = open(filename)
    structure = fhand.read()
    fhand.close()
    return structure


def get_fields_to_replace(text, prefix=''):
    return set(filter(lambda x: x.startswith(prefix), re.findall('\{([^\}]*)\}', text)))


def get_zone_list(zones_df):
    zone_list = ''
    for index, row in zones_df.iterrows():
        zone_list += re.sub('\{zone_name\}', 'ZON-' + row['zn_code'], ZONE_STRING) + '\n'

    zone_list = zone_list.rstrip() #remove unnecessary \n
    return zone_list


def create_responsible_part(con, responsible_df, zones_df):
    structure = read_structure('resp.txt')
    resp_to_replace = get_fields_to_replace(structure, prefix='resp')

    responsible_string = ''

    for index, row in responsible_df.iterrows():
        actual_person = sub_all(resp_to_replace, row, structure)
        # todo hardcode
        actual_person = re.sub('\{zone_list\}', get_zone_list(zones_df), actual_person)
        responsible_string += actual_person

    return responsible_string


def sub_all(from_list, to_df, text):
    for r in from_list:
        if '.' in r:
            column = r.split('.')[1]
        else:
            column = r
        text = re.sub('\{' + r + '\}', str(to_df[column]), text)
    return text


def get_pollutants_for_zone(con, zone_code):
    structure = read_structure('pollutants.txt')

    q = GET_POLLUTANT_QUERY.format(zn_code=zone_code)
    pollutant_df = pd.read_sql_query(q, con)

    poll_to_replace = get_fields_to_replace(structure)

    pollutant_string = ''

    for index, row in pollutant_df.iterrows():
        pollutant_string += sub_all(poll_to_replace, row, structure) + '\n'

    pollutant_string = pollutant_string.rstrip()
    return pollutant_string


def create_zones(con, zones_df, responsible_person):
    structure = read_structure('zones.txt')
    resp_to_replace = get_fields_to_replace(structure, prefix='resp')
    zone_to_replace = get_fields_to_replace(structure, prefix='zone')
    zones_string = ''

    for index, row in zones_df.iterrows():
        # first replace the responsible person
        actual_zone = sub_all(resp_to_replace, responsible_person, structure)
        # then replace zone data
        actual_zone = sub_all(zone_to_replace, row, actual_zone)
        # finally replace pollution
        actual_zone = re.sub('\{pollutants_list\}',
                             get_pollutants_for_zone(con, row['zn_code']), actual_zone)
        zones_string += actual_zone + '\n'

    zones_string = zones_string.rstrip()
    return zones_string


def create_xml_structure(con, responsible_df, zones_df):
    responsible = create_responsible_part(con, responsible_df, zones_df)
    # todo in case of more responsible....
    zones = create_zones(con, zones_df, responsible_df.iloc[0])
    header = read_structure('header.txt')

    xml = re.sub('\{responsible_xml_part\}', responsible, header)
    xml = re.sub('\{zones_xml_part\}', zones, xml)

    return xml


def save_xml(xml, filename='B.xml'):
    f = io.open(filename, 'w+', encoding="utf-8")
    f.write(xml)
    f.close()


def main(drv, mdb):

    con = init_connection(drv, mdb)

    zones_df = pd.read_sql_query(GET_ZONES_QUERY, con)
    responsible_df = pd.read_sql_query(GET_RESPONSIBLE_QUERY, con)

    xml = create_xml_structure(con, responsible_df, zones_df)

    save_xml(xml)

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])



