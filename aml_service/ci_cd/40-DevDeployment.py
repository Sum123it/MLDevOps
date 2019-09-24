"""
Copyright (C) Microsoft Corporation. All rights reserved.​
 ​
Microsoft Corporation (“Microsoft”) grants you a nonexclusive, perpetual,
royalty-free right to use, copy, and modify the software code provided by us
("Software Code"). You may not sublicense the Software Code or any use of it
(except to your affiliates and to vendors to perform work on your behalf)
through distribution, network access, service agreement, lease, rental, or
otherwise. This license does not purport to express any claim of ownership over
data you may have shared with Microsoft in the creation of the Software Code.
Unless applicable law gives you more rights, Microsoft reserves all other
rights not expressly granted herein, whether by implication, estoppel or
otherwise. ​
 ​
THE SOFTWARE CODE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
MICROSOFT OR ITS LICENSORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR
BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER
IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
ARISING IN ANY WAY OUT OF THE USE OF THE SOFTWARE CODE, EVEN IF ADVISED OF THE
POSSIBILITY OF SUCH DAMAGE.
"""
import os, json
from azureml.core import Workspace
from azureml.core.model import Model, InferenceConfig
from azureml.core.webservice import AciWebservice
from azureml.core.authentication import AzureCliAuthentication

# Load the JSON settings file and relevant section
print("Loading settings")
with open(os.path.join("aml_service", "settings.json")) as f:
    settings = json.load(f)
workspace_config_settings = settings["workspace"]["config"]
deployment_settings = settings["deployment"]
aci_settings = settings["compute_target"]["deployment"]["aci"]

# Loading Model Profile
print("Loading Model Profile")
with open(os.path.join("aml_service", "profiling_result.json")) as f:
    profiling_result = json.load(f)

# Get Workspace
print("Loading Workspace")
cli_auth = AzureCliAuthentication()
ws = Workspace.from_config(path=workspace_config_settings["path"], auth=cli_auth, _file_name=workspace_config_settings["file_name"])
print(ws.name, ws.resource_group, ws.location, ws.subscription_id, sep="\n")

# Loading Model
print("Loading Model")
model = Model(workspace=ws, name=deployment_settings["model"]["name"])

# Create image registry configuration 
if deployment_settings["image"]["docker"]["custom_image"]:
    container_registry = ContainerRegistry()
    container_registry.address = deployment_settings["image"]["docker"]["custom_image_registry_details"]["address"]
    container_registry.username = deployment_settings["image"]["docker"]["custom_image_registry_details"]["username"]
    container_registry.password = deployment_settings["image"]["docker"]["custom_image_registry_details"]["password"]
else:
    container_registry = None

# Defining inference config
print("Defining InferenceConfig")
inference_config = InferenceConfig(entry_script=deployment_settings["image"]["entry_script"],
                                   source_directory=deployment_settings["image"]["source_directory"],
                                   runtime=deployment_settings["image"]["runtime"],
                                   conda_file=deployment_settings["image"]["conda_file"],
                                   extra_docker_file_steps=deployment_settings["image"]["docker"]["extra_docker_file_steps"],
                                   enable_gpu=deployment_settings["image"]["docker"]["use_gpu"],
                                   description=deployment_settings["image"]["description"],
                                   base_image=deployment_settings["image"]["docker"]["custom_image"],
                                   base_image_registry=container_registry,
                                   cuda_version=deployment_settings["image"]["docker"]["cuda_version"])

try:
    print("Trying to update existing ACI service")
    dev_service = AciWebservice(workspace=ws, name=deployment_settings["dev_deployment"]["name"])
    dev_service.update(models=[model], inference_config=inference_config)
    print("Successfully updated existing ACI service")
except:
    print("Failed to update ACI service... Creating new ACI instance")
    aci_config = AciWebservice.deploy_configuration(cpu_cores=profiling_result["cpu"],
                                                   memory_gb=profiling_result["memory"],
                                                   tags=aci_settings["tags"],
                                                   properties=aci_settings["properties"],
                                                   description=aci_settings["description"])
    dev_service = Model.deploy(workspace=ws,
                               name=#TODO,
                               models=[model],
                               inference_config=inference_config,
                               deployment_config=aci_config)
    dev_service.wait_for_deployment(show_output=True)

print("Testing ACI web service")
#TODO
input_j = [[1, 2, 3, 4, 5, 6, 7, 8, 9, 10], [10, 9, 8, 7, 6, 5, 4, 3, 2, 1]]
print(input_j)
test_sample = json.dumps({"data": input_j})
test_sample = bytes(test_sample, encoding="utf8")
try:
    prediction = dev_service.run(input_data=test_sample)
    print(prediction)
except Exception as e:
    result = str(e)
    print(result)
    raise Exception("ACI service is not working as expected")

# Delete aci after test
print("Deleting ACI after successful test")
dev_service.delete()