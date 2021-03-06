import click
import git
import time
from git import Repo
from utils import Utils
from tabulate import tabulate
from error import Error
from confirmation import Confirmation
import colorama

class Repository:

	def __init__(self, repo, utils, tfs):
		self.repo = repo
		self.git = repo.git
		self.utils = utils
		self.tfs = tfs

	def create_feature(self, feature_name):
		self.utils.assert_is_not_dirty()
		self.utils.assert_feature_does_not_exists(feature_name)
		try:
			self.git.checkout("-B", feature_name, "master")
			self.git.checkout("master")
			self.repo.head.reset(commit="origin/master", working_tree=True)
			self.git.checkout(feature_name)

			Utils.print_encoded(click.style("New feature created successfully", bold=True))
		except git.exc.GitCommandError as command_error:
			Utils.print_encoded(command_error.stderr.decode("UTF-8"))
			Error.abort("Couldn't create new feature")

	def list_features(self):
		current_feature = self.utils.current_feature_name()
		features = [head.name for head in filter(lambda h: h.name != "master", self.repo.heads)]
		pull_request_details = self.tfs.get_pull_request_details(self.utils.current_repo_name(), features)

		table_of_features = []
		for pr_detail in pull_request_details:
			if pr_detail[0] == current_feature:
				line = [click.style("->", bold=True), pr_detail[1]["status"].describe(bold=True), click.style(pr_detail[0], bold=True), click.style(pr_detail[1]["title"], bold=True)]
			else:
				line = ["", pr_detail[1]["status"].describe(), pr_detail[0], pr_detail[1]["title"]]
			table_of_features.append(line)

		Utils.print_encoded(tabulate(table_of_features, headers=["", "Status", "Feature", "Pull request title"]))		

	def finish_feature(self, feature_name, delete_on_remote=False):
		repo_name = self.utils.current_repo_name()
		if not feature_name: 
			feature_name = self.utils.current_feature_name()
		self.utils.assert_is_not_dirty()
		self.utils.assert_feature_exists(feature_name)
		Error.abort_if(feature_name == "master", "You cannot finish your master feature")
		Error.abort_if(self.tfs.has_active_pull_request(repo_name, feature_name), "You have an active pull request on that branch.\nPlease complete it or abandon it to continue")
		Confirmation.show_if(self.utils.has_unpushed_commits(feature_name), "You have unpushed commits on this branch")

		if feature_name == self.utils.current_feature_name():
			self.move_to_feature("master")

		try:
			self.git.branch("-D", feature_name)
			if delete_on_remote:
				self.git.push("origin", "--delete", feature_name)
			if self.utils.current_feature_name() == "master":
				Utils.print_encoded(click.style("Updating master", bold=True))
				self.update_feature(silent=True)

			Utils.print_encoded("Finished feature " + click.style(feature_name, bold=True))
		except git.exc.GitCommandError as command_error:
			Utils.print_encoded(command_error.stderr.decode("UTF-8"))
			Error.abort("Couldn't finish feature")

	def move_to_feature(self, feature_name):
		self.utils.assert_is_not_dirty()
		self.utils.assert_feature_exists(feature_name)
		try:
			self.git.checkout(feature_name)
			Utils.print_encoded("Moved to feature " + click.style(feature_name, bold=True))
		except git.exc.GitCommandError as command_error:
			Utils.print_encoded(command_error.stderr.decode("UTF-8"))
			Error.abort("Couldn't move to feature")

	def review_feature(self, title, hotfix):
		repo_name = self.utils.current_repo_name()
		current_feature = self.utils.current_feature_name()
		if current_feature == "master":
			if not title: title = self.utils.obtain_pull_request_title_from_last_commit()
			current_feature = Utils.create_feature_name_from_title(title)
			self.create_feature(current_feature)

		self.share_feature(silent=True)
		if not self.tfs.has_active_pull_request(repo_name, current_feature):
			if not title: title = self.utils.obtain_pull_request_title_from_last_commit()
			if hotfix: title = '[HOTFIX] ' + title
			response = self.tfs.create_pull_request(repo_name, current_feature, title)
			Error.abort_if(response.status_code != 201, "Request error - HTTP_CODE: " + str(response.status_code) + "\n\n" + response.json()["message"] if "message" in response.json() else "")
			Utils.print_encoded(click.style("Pull request successfully created", bold=True))
		else:
			Utils.print_encoded(click.style("Pull request successfully updated", bold=True))

		if hotfix:
			self.tfs.approve_pull_request(repo_name, current_feature)
			Utils.print_encoded(click.style("[HOTFIX] ", bold=True, fg="red") + click.style("Pull request successfully merged into master", bold=True))
			time.sleep(0.5)
			self.finish_feature(current_feature, delete_on_remote=True)

	def share_feature(self, silent=False):
		current_feature = self.utils.current_feature_name()
		Error.abort_if(current_feature == "master", "You cannot push changes on master")
		try:
			output = self.git.push("--set-upstream", "origin", current_feature)
			if not silent:
				Utils.print_encoded(click.style("Feature shared successfully", bold=True))
		except git.exc.GitCommandError as command_error:
			Utils.print_encoded(command_error.stderr.decode("UTF-8"))
			Error.abort("Couldn't share feature")

	def update_feature(self, silent=False):
		try:
			output = self.git.pull("origin", "master")
			if not silent:
				Utils.print_encoded(click.style("\nFeature successfully updated", bold=True))
		except git.exc.GitCommandError as command_error:
			if command_error.status == 1:
				Utils.print_encoded(click.style("\nFeature updated but conflicts were found", bold=True))
				Utils.print_encoded(click.style("Fix them up in the work tree, and then use 'git add/rm <file>' as appropriate"))
			else:
				Utils.print_encoded(command_error.stderr.decode("UTF-8"))
				Error.abort("Couldn't update feature")
