# Configure Aviatrix provider source and version
terraform {
  required_providers {
    aviatrix = {
      source  = "AviatrixSystems/aviatrix"
      version = "3.2.2"
    }
  }
  cloud {
    workspaces {
      name = "43_github_workflow_tf_apply_approval"
    }
  }
}

# Configure Aviatrix provider
provider "aviatrix" {
  controller_ip           = var.controller_ip
  username                = "admin"
  password                = var.controller_password
  skip_version_validation = false
  verify_ssl_certificate  = false
}