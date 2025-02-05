import json
import sys
import time

sys.path.append("../MachineManager")

import ClusterAPI
import cluster_settings

class Task:
	def __init__(self,name,machineList):
		self.name = name
		self.machineList = machineList

def get_ps_job(task_id):
	DockerFileName = "TF_PS_GPU"
	DockerBuildPath = "../"
	Port = "2222"
	job = ClusterAPI.Job(DockerFileName,DockerBuildPath,Port,"ps","not_started")
	job.set_TaskId(task_id)
	return job

def get_worker_job(task_id):
	DockerFileName = "TF_WORKER_GPU"
	DockerBuildPath = "../"
	Port = "2222"
	job = ClusterAPI.Job(DockerFileName,DockerBuildPath,Port,"worker","not_started")
	job.set_TaskId(task_id)
	return job

def get_single_job():
	DockerFileName = "TF_SINGLE_GPU"
	DockerBuildPath = "../"
	Port = "2222"
	return ClusterAPI.Job(DockerFileName,DockerBuildPath,Port,"single","not_started")

def get_machine(ip_address,machine_type,job):
	return ClusterAPI.Machine(ip_address,machine_type,job) 


def get_task_name(dataset_name,network_name):
	return time.strftime('%Y:%m:%d:%H:%M:%S',time.localtime(time.time()))+":"+dataset_name+":"+network_name

def set_Task_Param_Single(cluster,json_data,task_name):
	batch_size = json_data['batch_size']
	learning_rate = json_data['learning_rate']
	network = json_data['network']
	dataset_url = json_data['dataset_url']

	param = {}
	param['batch_size'] = batch_size
	param['learning_rate'] = learning_rate
	param['dataset_url'] = dataset_url
	param['network'] = network

	cluster.UpdateTaskParam(task_name,param)

def set_Task_Param(cluster,json_data,task_name,ps_spec,worker_spec,port):
	batch_size = json_data['batch_size']
	learning_rate = json_data['learning_rate']
	network = json_data['network']
	dataset_url = json_data['dataset_url']

	param = {}
	param['batch_size'] = batch_size
	param['learning_rate'] = learning_rate
	param['dataset_url'] = dataset_url
	param['network'] = network
	param['ps_spec'] = ps_spec
	param['worker_spec'] = worker_spec
	param['port'] = port

	cluster.UpdateTaskParam(task_name,param)


def Train(json_data):
	# connect_url = ["localhost:27017"]
	connect_url = cluster_settings.connect_url
	cluster = ClusterAPI.Cluster(connect_url)
	nodes = cluster.get_AviableMachines()
	print(nodes)
	if len(nodes)>1:
		machineList = []
		ps_machine = get_machine(nodes[0],"gpu",get_ps_job(0))
		machineList.append(ps_machine)
		for i in range(1,len(nodes)):
			worker_machine = get_machine(nodes[i],"gpu",get_worker_job(i-1))
			machineList.append(worker_machine)
		dataset_name = json_data['dataset_name']
		network_name = json_data['network_name']
		task_name = get_task_name(dataset_name,network_name)
		task = ClusterAPI.Task(task_name,machineList)
		ps_spec = [nodes[0]]
		worker_spec = nodes[1:]
		set_Task_Param(cluster,json_data,task_name,ps_spec,worker_spec,"2222")
		cluster.AddTask(task)
		error_list = cluster.AssignTask(task)
	elif len(nodes)==1:
		machineList = []
		single_machine = get_machine(nodes[0],"gpu",get_single_job())
		machineList.append(single_machine)
		dataset_name = json_data['dataset_name']
		network_name = json_data['network_name']
		task_name = get_task_name(dataset_name,network_name)
		task = ClusterAPI.Task(task_name,machineList)
		set_Task_Param_Single(cluster,json_data,task_name)
		cluster.AddTask(task)
		error_list = cluster.AssignTask(task)
		print(task_name)


json_data = {}
json_data['dataset_name'] = "cifar-10"
json_data['network_name'] = "conv_net"
json_data['batch_size'] = 200
json_data['learning_rate'] = 0.01
json_data['dataset_url'] = "./cifar-10-batches-py"
with open('./test.json',"r") as json_file:
	json_obj = json.load(json_file)
network = json.dumps(json_obj)
json_data['network'] = network

Train(json_data)
