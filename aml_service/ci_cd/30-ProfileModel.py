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
import os, sys, json, azureml.core
from azureml.core import Workspace, ContainerRegistry, Environment
from azureml.core.model import Model, InferenceConfig
from azureml.core.image import Image, ContainerImage
from azureml.core.conda_dependencies import CondaDependencies
from azureml.core.authentication import AzureCliAuthentication
from helper import utils

sys.path.insert(0, os.path.join("code", "testing"))
import test_functions

# Load the JSON settings file and relevant sections
print("Loading settings")
with open(os.path.join("aml_service", "settings.json")) as f:
    settings = json.load(f)
deployment_settings = settings["deployment"]
env_name = settings["experiment"]["name"]  + "_deployment"

# Get workspace
print("Loading Workspace")
cli_auth = AzureCliAuthentication()
config_file_path = os.environ.get("GITHUB_WORKSPACE", default="aml_service")
config_file_name = "aml_arm_config.json"
ws = Workspace.from_config(
    path=config_file_path,
    auth=cli_auth,
    _file_name=config_file_name)
print(ws.name, ws.resource_group, ws.location, ws.subscription_id, sep = '\n')

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

# Creating dependencies
print("Creating dependencies and registering environment")
conda_dep = CondaDependencies.create(conda_packages=deployment_settings["image"]["dependencies"]["conda_packages"],
                                     pip_packages=deployment_settings["image"]["dependencies"]["pip_packages"],
                                     python_version=deployment_settings["image"]["dependencies"]["python_version"],
                                     pin_sdk_version=deployment_settings["image"]["dependencies"]["pin_sdk_version"])
dep_path = os.path.join("code", "scoring", "myenv.yml")
conda_dep.save(path=dep_path)

# Creating InferenceConfig
print("Creating InferenceConfig")
if deployment_settings["image"]["use_custom_environment"]:
    env = utils.get_environment(name_suffix="_deployment")
    inferenceConfig = InferenceConfig(entry_script=deployment_settings["image"]["entry_script"],
                                      source_directory=deployment_settings["image"]["source_directory"],
                                      runtime=deployment_settings["image"]["runtime"],
                                      environment=env)
else:
    inference_config = InferenceConfig(entry_script=deployment_settings["image"]["entry_script"],
                                       source_directory=deployment_settings["image"]["source_directory"],
                                       runtime=deployment_settings["image"]["runtime"],
                                       conda_file=os.path.basename(dep_path),
                                       extra_docker_file_steps=deployment_settings["image"]["docker"]["extra_docker_file_steps"],
                                       enable_gpu=deployment_settings["image"]["docker"]["use_gpu"],
                                       description=deployment_settings["image"]["description"],
                                       base_image=deployment_settings["image"]["docker"]["custom_image"],
                                       base_image_registry=container_registry,
                                       cuda_version=deployment_settings["image"]["docker"]["cuda_version"])

# Registering Environment
print("Registering Environment")
if "env" not in locals():
    env = Environment.from_conda_specification(name=env_name, file_path=dep_path)
registered_env = env.register(workspace=ws)
print("Registered Environment")
print(registered_env.name, "Version: " + registered_env.version, sep="\n")

# Profile model
print("Profiling Model")
test_sample = test_functions.get_test_data_sample()
profile = Model.profile(workspace=ws,
                        profile_name=deployment_settings["image"]["name"],
                        models=[model],
                        inference_config=inference_config,
                        input_data=test_sample)
profile.wait_for_profiling(show_output=True)
print(profile.get_results(), profile.recommended_cpu, profile.recommended_cpu_latency, profile.recommended_memory, profile.recommended_memory_latency, sep="\n")

# Writing the profiling results to /aml_service/profiling_result.json
profiling_result = {}
profiling_result["cpu"] = profile.recommended_cpu
profiling_result["memory"] = profile.recommended_memory
profiling_result["image_id"] = profile.image_id
with open(os.path.join("aml_service", "profiling_result.json"), "w") as outfile:
    json.dump(profiling_result, outfile)