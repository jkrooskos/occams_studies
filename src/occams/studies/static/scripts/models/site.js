/**
 * Client-side Site Model
 */
function Site(data){
  var self = this;

  self.__src__ = ko.observable();

  self.id = ko.observable();
  self.name = ko.observable();
  self.title = ko.observable();

  /**
   * Update instance properties
   */
  self.update = function(data){
    ko.mapping.fromJS(data, {}, self);
  };

  /**
   * Serializes object for transport to server
   */
  self.toJS = function(){
    return ko.mapping.toJS(self, {
      include: ['id', 'name', 'title']
    });
  };

  // Apply initial data
  self.update(data);
}

Site.availableOptions = ko.observableArray();
