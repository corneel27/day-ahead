import sys

from webserver.app import app
from flask import render_template, request
import json, os, fnmatch

#sys.path.append("../")
from prog.da_config import Config
import prog.da_report

web_datapath = "static/data/"
app_datapath = "app/static/data/"
images_folder = os.path.join(web_datapath, 'images')
config = Config(app_datapath + "options.json")

def get_file_list(path:str, filter:str):
    """
    """
    flist = []
    #path = os.path.join(path, "/")
    for f in os.listdir(path):
        if fnmatch.fnmatch(f, filter):
            fullname = os.path.join(path, f)
            flist.append({"name": f, "time": os.path.getmtime(fullname)})
            #print(f, time.ctime(os.path.getmtime(f)))
    flist.sort(key=lambda x: x.get('time'), reverse=True)
    return flist

@app.route('/settings/<filename>', methods=['POST', 'GET'])
def settings(filename):
    message = None
    filename_ext = app_datapath + filename + ".json"
    if request.method == 'POST':
        updated_data = request.form["codeinput"]
        try:
            json_data = json.loads(updated_data)
            # Update the JSON data
            with open(filename_ext, 'w') as f:
                f.write(updated_data)
            message = 'JSON data updated successfully'
        except Exception as err:
            message = 'Error: ' + err.args[0]
        options = updated_data
    else:
        # Load initial JSON data from a file
        with open(filename_ext, 'r') as f:
            options = f.read()
    return render_template('settings.html', title='Instellingen', options_data=options, message=message)

@app.route('/', methods=['POST', 'GET'])
@app.route('/home', methods=['POST', 'GET'])
def optimalisering():
    subjects = ["grid"]
    views = ["grafiek", "tabel"]
    active_subject = "grid"
    active_view = "grafiek"
    active_time = None
    action = None
    battery_options = config.get(["battery"])
    for b in range(len(battery_options)):
        subjects.append(battery_options[b]["name"])
    if request.method == 'POST':
        #ImmutableMultiDict([('cur_subject', 'Accu2'), ('subject', 'Accu1')])
        list = request.form.to_dict(flat=False)
        if "cur_subject" in list:
            active_subject = list["cur_subject"][0]
        if "cur_view" in list:
            active_view = list["cur_view"][0]
        if "subject" in list:
            active_subject = list["subject"][0]
        if "view" in list:
            active_view = list["view"][0]
        if "active_time" in list:
            active_time = float(list["active_time"][0])
        if "action" in list:
            action = list["action"][0]

    if active_view == "grafiek":
        active_map = "/images/"
        active_filter = "optimum*.png"
    else:
        active_map = "/log/"
        active_filter = "calc_optimum*.log"
    flist = get_file_list(app_datapath+active_map, active_filter)
    index = 0
    if active_time:
        for i in range(len(flist)):
            if flist[i]["time"] == active_time:
                index = i
                break
    if action == "first":
        index = 0
    if action == "previous":
        index = max (0, index - 1)
    if action == "next":
        index = min (len(flist)-1, index + 1)
    if action == "last":
        index = len(flist)-1
    if action == "delete":
        os.remove(app_datapath + active_map + flist[index]["name"])
        flist = get_file_list(app_datapath+active_map, active_filter)
        index = min(len(flist) - 1, index)
    active_time = str(flist[index]["time"])
    if active_view == "grafiek":
        image = os.path.join(web_datapath+active_map, flist[index]["name"])
        tabel = None
    else:
        image = None
        with open(app_datapath+active_map + flist[index]["name"], 'r') as f:
            tabel = f.read()

    return render_template('optimalisering.html', title='Optimalisering', subjects=subjects, views=views,
                           active_subject=active_subject, active_view=active_view, image=image, tabel=tabel,
                           active_time=active_time)

@app.route('/reports', methods=['POST', 'GET'])
def reports():
    report = prog.da_report.Report()
    subjects =["verbruik", "kosten"]
    active_subject = "verbruik"
    views = ["grafiek", "tabel"]
    active_view = "tabel"
    periode_options = report.periodes.keys()
    active_period = "vandaag"
    if request.method in ['POST', 'GET']:
        #ImmutableMultiDict([('cur_subject', 'Accu2'), ('subject', 'Accu1')])
        list = request.form.to_dict(flat=False)
        if "cur_subject" in list:
            active_subject = list["cur_subject"][0]
        if "cur_view" in list:
            active_view = list["cur_view"][0]
        if "cur_periode" in list:
            active_period = list["cur_periode"]
        if "subject" in list:
            active_subject = list["subject"][0]
        if "view" in list:
            active_view = list["view"][0]
        if "periode-select" in list:
            active_period = list["periode-select"][0]
    active_interval = report.periodes[active_period]["interval"]
    report_df = report.get_grid_data(active_period)
    filtered_df = report.calc_columns(report_df, active_interval, active_view)
    filtered_df.round(1)
    if active_view == "tabel":
        tables = [filtered_df.to_html(index=False, justify="right", decimal=",", classes="data", border=0) ]
    else:
        d = filtered_df.values.tolist()
        c = filtered_df.columns.tolist()
        d.insert(0, c)
        options = {
            "title": active_subject + " " + active_period,
            "vAxis": {"title": 'Verbruik'},
            "hAxis": {"title": filtered_df.columns[0][0]},
            "seriesType": 'bars',
            "series": {6: {"type": 'line'}}
        }
        tables = json.dumps({"options":options, 'data': d})
    return render_template('report.html', title='Rapportage', subjects=subjects, views=views,
                           periode_options=periode_options, active_period=active_period,
                           active_subject=active_subject, active_view=active_view, tables=tables)
