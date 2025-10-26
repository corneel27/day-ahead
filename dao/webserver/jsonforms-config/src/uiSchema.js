// UI Schema for Day Ahead Optimizer Configuration
// This defines the layout and organization of the configuration form

export const uiSchema = {
  "type": "Categorization",
  "elements": [
    {
      "type": "Category",
      "label": "General",
      "elements": [
        {
          "type": "VerticalLayout",
          "elements": [
            {
              "type": "Group",
              "label": "Optimization Settings",
              "elements": [
                {
                  "type": "Control",
                  "scope": "#/properties/interval"
                },
                {
                  "type": "Control",
                  "scope": "#/properties/strategy"
                },
                {
                  "type": "Control",
                  "scope": "#/properties/max_gap"
                },
                {
                  "type": "Control",
                  "scope": "#/properties/grid/properties/max_power",
                  "label": "Grid Max Power (kW)"
                }
              ]
            },
            {
              "type": "Group",
              "label": "Base Load Configuration",
              "elements": [
                {
                  "type": "Control",
                  "scope": "#/properties/use_calc_baseload"
                },
                {
                  "type": "Control",
                  "scope": "#/properties/baseload calc periode",
                  "rule": {
                    "effect": "SHOW",
                    "condition": {
                      "scope": "#/properties/use_calc_baseload",
                      "schema": {
                        "const": "True"
                      }
                    }
                  }
                },
                {
                  "type": "Control",
                  "scope": "#/properties/baseload",
                  "rule": {
                    "effect": "SHOW",
                    "condition": {
                      "scope": "#/properties/use_calc_baseload",
                      "schema": {
                        "const": "False"
                      }
                    }
                  }
                }
              ]
            }
          ]
        }
      ]
    },
    {
      "type": "Category",
      "label": "Database",
      "elements": [
        {
          "type": "VerticalLayout",
          "elements": [
            {
              "type": "Group",
              "label": "Home Assistant",
              "elements": [
                {
                  "type": "Control",
                  "scope": "#/properties/homeassistant"
                }
              ]
            },
            {
              "type": "Group",
              "label": "Home Assistant Database",
              "elements": [
                {
                  "type": "Control",
                  "scope": "#/properties/database ha"
                }
              ]
            },
            {
              "type": "Group",
              "label": "Day Ahead Database",
              "elements": [
                {
                  "type": "Control",
                  "scope": "#/properties/database da"
                }
              ]
            }
          ]
        }
      ]
    },
    {
      "type": "Category",
      "label": "Dashboard",
      "elements": [
        {
          "type": "VerticalLayout",
          "elements": [
            {
              "type": "Group",
              "label": "Dashboard",
              "elements": [
                {
                  "type": "Control",
                  "scope": "#/properties/logging level"
                },
                {
                  "type": "Control",
                  "scope": "#/properties/dashboard"
                }
              ]
            },
            {
              "type": "Group",
              "label": "Graphics Settings",
              "elements": [
                {
                  "type": "Control",
                  "scope": "#/properties/graphical backend"
                },
                {
                  "type": "Control",
                  "scope": "#/properties/graphics"
                }
              ]
            }
          ]
        }
      ]
    },
    {
      "type": "Category",
      "label": "Prices",
      "elements": []
    },
    {
      "type": "Category",
      "label": "Optimisations",
      "elements": [
        {
          "type": "Categorization",
          "elements": [
            {
              "type": "Category",
              "label": "Solar",
              "elements": [
                {
                  "type": "VerticalLayout",
                  "elements": [
                    {
                      "type": "Group",
                      "label": "Solar PV Systems (AC)",
                      "elements": [
                        {
                          "type": "Control",
                          "scope": "#/properties/solar"
                        }
                      ]
                    }
                  ]
                }
              ]
            },
            {
              "type": "Category",
              "label": "Battery",
              "elements": [
                {
                  "type": "VerticalLayout",
                  "elements": [
                    {
                      "type": "Group",
                      "label": "Battery Systems",
                      "elements": [
                        {
                          "type": "Control",
                          "scope": "#/properties/battery"
                        }
                      ]
                    }
                  ]
                }
              ]
            },
            {
              "type": "Category",
              "label": "Electric Vehicle",
              "elements": [
                {
                  "type": "VerticalLayout",
                  "elements": [
                    {
                      "type": "Group",
                      "label": "Electric Vehicles",
                      "elements": [
                        {
                          "type": "Control",
                          "scope": "#/properties/electric vehicle"
                        }
                      ]
                    }
                  ]
                }
              ]
            },
            {
              "type": "Category",
              "label": "Appliance",
              "elements": [
                {
                  "type": "VerticalLayout",
                  "elements": [
                    {
                      "type": "Group",
                      "label": "Household Appliances",
                      "elements": [
                        {
                          "type": "Control",
                          "scope": "#/properties/machines"
                        }
                      ]
                    }
                  ]
                }
              ]
            },
            {
              "type": "Category",
              "label": "Boiler",
              "elements": [
                {
                  "type": "VerticalLayout",
                  "elements": [
                    {
                      "type": "Group",
                      "label": "Hot Water Boiler",
                      "elements": [
                        {
                          "type": "Control",
                          "scope": "#/properties/boiler"
                        }
                      ]
                    }
                  ]
                }
              ]
            },
            {
              "type": "Category",
              "label": "Heating",
              "elements": [
                {
                  "type": "VerticalLayout",
                  "elements": [
                    {
                      "type": "Group",
                      "label": "Heat Pump",
                      "elements": [
                        {
                          "type": "Control",
                          "scope": "#/properties/heating"
                        }
                      ]
                    }
                  ]
                }
              ]
            }
          ]
        }
      ]
    },
    {
      "type": "Category",
      "label": "Reports",
      "elements": []
    },
    {
      "type": "Category",
      "label": "Scheduler",
      "elements": []
    },
    {
      "type": "Category",
      "label": "Weather & Prices",
      "elements": [
        {
          "type": "VerticalLayout",
          "elements": [
            {
              "type": "Group",
              "label": "Weather Data (Meteoserver)",
              "elements": [
                {
                  "type": "Control",
                  "scope": "#/properties/meteoserver-key"
                },
                {
                  "type": "Control",
                  "scope": "#/properties/meteoserver-model"
                },
                {
                  "type": "Control",
                  "scope": "#/properties/meteoserver-attempts"
                }
              ]
            },
            {
              "type": "Group",
              "label": "Energy Prices",
              "elements": [
                {
                  "type": "Control",
                  "scope": "#/properties/prices"
                }
              ]
            }
          ]
        }
      ]
    },
    {
      "type": "Category",
      "label": "System",
      "elements": [
        {
          "type": "VerticalLayout",
          "elements": [
            {
              "type": "Group",
              "label": "Notifications",
              "elements": [
                {
                  "type": "Control",
                  "scope": "#/properties/notifications"
                }
              ]
            },
            {
              "type": "Group",
              "label": "Dashboard",
              "elements": [
                {
                  "type": "Control",
                  "scope": "#/properties/dashboard"
                }
              ]
            },
            {
              "type": "Group",
              "label": "History",
              "elements": [
                {
                  "type": "Control",
                  "scope": "#/properties/history"
                }
              ]
            }
          ]
        }
      ]
    },
    {
      "type": "Category",
      "label": "Reporting",
      "elements": [
        {
          "type": "VerticalLayout",
          "elements": [
            {
              "type": "Group",
              "label": "Report Entities",
              "elements": [
                {
                  "type": "Control",
                  "scope": "#/properties/report"
                }
              ]
            },
            {
              "type": "Group",
              "label": "Tibber Integration",
              "elements": [
                {
                  "type": "Control",
                  "scope": "#/properties/tibber"
                }
              ]
            }
          ]
        }
      ]
    },
    {
      "type": "Category",
      "label": "Scheduler",
      "elements": [
        {
          "type": "VerticalLayout",
          "elements": [
            {
              "type": "Group",
              "label": "Task Scheduler",
              "elements": [
                {
                  "type": "Control",
                  "scope": "#/properties/scheduler"
                }
              ]
            }
          ]
        }
      ]
    }
  ]
};
