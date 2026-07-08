module "mc-spoke" {
  source  = "terraform-aviatrix-modules/mc-spoke/aviatrix"
  version = "1.7.1"

  account  = var.aviatrix_account
  region   = "us-east-1"
  name     = "ue1spoke1"
  cloud    = "AWS"
  cidr     = "10.1.1.0/24"
  attached = false
}
